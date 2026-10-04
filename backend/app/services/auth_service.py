"""Authentication service.

Owns the business logic for register/login/refresh/logout. Routes stay thin:
parse request, call the service, translate service exceptions to HTTP
responses, return. All of this logic is unit-testable without spinning up
FastAPI at all, since it only depends on an AsyncSession and Settings.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.membership import MembershipRole
from app.models.user import User
from app.repositories.membership_repository import MembershipRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.services.exceptions import (
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int


@dataclass(frozen=True)
class RegistrationResult:
    user: User
    organization_id: uuid.UUID


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._users = UserRepository(session)
        self._organizations = OrganizationRepository(session)
        self._memberships = MembershipRepository(session)
        self._refresh_tokens = RefreshTokenRepository(session)

    async def register(
        self, *, email: str, password: str, full_name: str, organization_name: str
    ) -> RegistrationResult:
        existing = await self._users.get_by_email(email)
        if existing is not None:
            raise EmailAlreadyRegisteredError(email)

        user = await self._users.create(
            email=email, hashed_password=hash_password(password), full_name=full_name
        )
        organization = await self._organizations.create_with_unique_slug(name=organization_name)
        # The user who creates an organization is its admin by construction —
        # there is no unauthenticated path to any other role.
        await self._memberships.create(
            user_id=user.id, organization_id=organization.id, role=MembershipRole.ADMIN
        )
        await self._session.commit()
        return RegistrationResult(user=user, organization_id=organization.id)

    async def login(self, *, email: str, password: str) -> tuple[User, IssuedTokens]:
        user = await self._users.get_by_email(email)
        # Deliberately identical error for "no such user" and "wrong password"
        # so the response can't be used to enumerate registered emails.
        if user is None or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError()
        if not user.is_active:
            raise InactiveUserError()

        tokens = await self._issue_tokens(user.id)
        await self._session.commit()
        return user, tokens

    async def refresh(self, *, raw_refresh_token: str) -> IssuedTokens:
        token_hash = hash_refresh_token(raw_refresh_token)
        stored = await self._refresh_tokens.get_by_hash(token_hash)
        if stored is None or not stored.is_valid:
            raise InvalidRefreshTokenError()

        user = await self._users.get_by_id(stored.user_id)
        if user is None or not user.is_active:
            raise InvalidRefreshTokenError()

        # Rotate: revoke the presented token and issue a brand new pair. This
        # means a leaked-but-unused refresh token becomes unusable the moment
        # the legitimate client refreshes, and reuse of a revoked token is a
        # detectable signal (not acted on further here, but logged).
        await self._refresh_tokens.revoke(stored)
        tokens = await self._issue_tokens(user.id)
        await self._session.commit()
        return tokens

    async def logout(self, *, raw_refresh_token: str) -> None:
        token_hash = hash_refresh_token(raw_refresh_token)
        stored = await self._refresh_tokens.get_by_hash(token_hash)
        if stored is not None and stored.is_valid:
            await self._refresh_tokens.revoke(stored)
            await self._session.commit()
        # Logging out with an already-invalid/unknown token is not an error —
        # the end state the caller wants (not logged in) is already true.

    async def _issue_tokens(self, user_id: uuid.UUID) -> IssuedTokens:
        access_token = create_access_token(
            subject=str(user_id),
            secret=self._settings.jwt_secret,
            algorithm=self._settings.jwt_algorithm,
            expires_minutes=self._settings.access_token_expire_minutes,
        )
        raw_refresh_token = generate_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=self._settings.refresh_token_expire_days)
        await self._refresh_tokens.create(
            user_id=user_id,
            token_hash=hash_refresh_token(raw_refresh_token),
            expires_at=expires_at,
        )
        return IssuedTokens(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            expires_in=self._settings.access_token_expire_minutes * 60,
        )
