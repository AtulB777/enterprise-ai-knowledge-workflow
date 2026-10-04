"""Password hashing and JWT helpers.

Password hashing uses argon2id (via argon2-cffi) — OWASP's current first
recommendation, actively maintained, no passlib/bcrypt version-detection issues.

JWTs are used only for short-lived access tokens. Refresh tokens are opaque
random values stored server-side (hashed) so they can be revoked — a JWT
refresh token can't be invalidated without a blocklist, which defeats the
point of using a JWT for it in the first place.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_password_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return _password_hasher.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return False


def create_access_token(
    *,
    subject: str,
    secret: str,
    algorithm: str,
    expires_minutes: int,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
        "type": "access",
        # Unique per token, not just per subject/second: without this, two
        # tokens issued for the same user within the same second (e.g. an
        # immediate register-then-refresh) are byte-for-byte identical,
        # since iat/exp only carry second resolution. A jti also gives each
        # issuance an identity for audit logs even though these tokens
        # aren't individually revocable (unlike refresh tokens).
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(token: str, *, secret: str, algorithm: str) -> dict[str, Any]:
    """Raises jwt.PyJWTError (or a subclass) on any invalid/expired token."""
    decoded: dict[str, Any] = jwt.decode(token, secret, algorithms=[algorithm])
    if decoded.get("type") != "access":
        raise jwt.InvalidTokenError("Not an access token")
    return decoded


def generate_refresh_token() -> str:
    """Opaque, high-entropy token. Only its hash is ever stored server-side."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    # SHA-256 is appropriate here (not a password hash use case): the token
    # itself already has 48 bytes of entropy, so we're hashing for lookup /
    # at-rest storage, not defending against brute force of a low-entropy secret.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
