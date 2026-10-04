"""Tests for the startup guard refusing to run in production with the known
default JWT secret (app/core/config.py). Constructs Settings directly rather
than going through get_settings()'s lru_cache, so each test gets a genuinely
fresh instance to validate against.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_refuses_to_start_in_production_with_default_secret() -> None:
    with pytest.raises(ValidationError, match="Refusing to start"):
        Settings(environment="production", jwt_secret="dev-only-insecure-secret-change-me")


def test_allows_production_with_a_real_secret() -> None:
    settings = Settings(
        environment="production",
        jwt_secret="a-genuinely-random-secret-generated-with-openssl",
    )
    assert settings.environment == "production"


def test_allows_development_with_the_default_secret() -> None:
    """The guard is specifically about production — development legitimately
    uses a known, shared default on purpose, and must not be blocked.
    """
    settings = Settings(environment="development", jwt_secret="dev-only-insecure-secret-change-me")
    assert settings.environment == "development"


def test_allows_test_environment_with_the_default_secret() -> None:
    settings = Settings(environment="test", jwt_secret="dev-only-insecure-secret-change-me")
    assert settings.environment == "test"
