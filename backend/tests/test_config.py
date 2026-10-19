import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_short_jwt_secret_is_rejected_outside_tests():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, env="production", database_url="x", jwt_secret="short")


def test_short_jwt_secret_is_allowed_in_test_env():
    settings = Settings(_env_file=None, env="test", database_url="x", jwt_secret="")
    assert settings.env == "test"


def test_defaults_match_the_locked_decisions():
    settings = Settings(_env_file=None, env="test", database_url="x")
    assert settings.access_token_minutes == 15
    assert settings.refresh_token_days == 7
    assert settings.run_embedded_worker is True
