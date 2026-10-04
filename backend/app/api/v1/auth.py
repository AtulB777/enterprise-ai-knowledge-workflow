from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.rate_limit import (
    check_failed_login_throttle,
    clear_failed_login_throttle,
    rate_limit_by_ip,
    record_failed_login,
)
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services.auth_service import AuthService
from app.services.exceptions import (
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)

router = APIRouter()

_settings_at_import = get_settings()
_login_rate_limit = rate_limit_by_ip(
    "login", limit=_settings_at_import.rate_limit_login_per_minute, window_seconds=60
)
_register_rate_limit = rate_limit_by_ip(
    "register", limit=_settings_at_import.rate_limit_register_per_hour, window_seconds=3600
)


def _get_auth_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthService:
    return AuthService(db, settings)


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=TokenResponse,
    dependencies=[Depends(_register_rate_limit)],
)
async def register(
    body: RegisterRequest,
    auth_service: Annotated[AuthService, Depends(_get_auth_service)],
) -> TokenResponse:
    try:
        await auth_service.register(
            email=body.email,
            password=body.password,
            full_name=body.full_name,
            organization_name=body.organization_name,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc

    # Registration immediately logs the user in — issue a real session rather
    # than making them log in again right after signing up.
    _, tokens = await auth_service.login(email=body.email, password=body.password)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(_login_rate_limit)])
async def login(
    body: LoginRequest,
    auth_service: Annotated[AuthService, Depends(_get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    # Checked before attempting password verification (ADR-017 decision 4)
    # — an already-locked-out account shouldn't pay the cost of a password
    # hash comparison it can't succeed at anyway, and this is specifically
    # about protecting *this account* from credential stuffing regardless
    # of how many different IPs the attempts come from.
    throttle = await check_failed_login_throttle(body.email, settings=settings)
    if not throttle.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many failed attempts for this account. "
                f"Try again in {throttle.retry_after_seconds} seconds."
            ),
            headers={"Retry-After": str(throttle.retry_after_seconds)},
        )

    try:
        _, tokens = await auth_service.login(email=body.email, password=body.password)
    except (InvalidCredentialsError, InactiveUserError) as exc:
        await record_failed_login(body.email, settings=settings)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        ) from exc

    # A genuine successful login shouldn't stay penalized by earlier failed
    # attempts once the account owner has actually proven who they are.
    await clear_failed_login_throttle(body.email, settings=settings)

    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    auth_service: Annotated[AuthService, Depends(_get_auth_service)],
) -> TokenResponse:
    try:
        tokens = await auth_service.refresh(raw_refresh_token=body.refresh_token)
    except InvalidRefreshTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        ) from exc

    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest,
    auth_service: Annotated[AuthService, Depends(_get_auth_service)],
) -> None:
    await auth_service.logout(raw_refresh_token=body.refresh_token)
