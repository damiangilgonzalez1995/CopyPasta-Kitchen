"""Tests of the base behaviour. They use `BaseAppSettings`, not `Settings`, so they keep passing
after blocks with required fields (e.g. MEMORY_BACKEND) are mixed into `Settings`."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings

from core import config
from core.config import BaseAppSettings


def test_env_vars_override_defaults(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "true")
    settings = BaseAppSettings(_env_file=None)
    assert settings.environment == "production"
    assert settings.debug is True


def test_get_settings_is_cached(monkeypatch):
    monkeypatch.setattr(config, "Settings", BaseAppSettings)
    config.get_settings.cache_clear()
    try:
        assert config.get_settings() is config.get_settings()
    finally:
        config.get_settings.cache_clear()


def test_blocks_compose_by_inheritance(monkeypatch):
    class PaymentsSettings(BaseSettings):
        payments_api_key: SecretStr | None = None

    class Composed(PaymentsSettings, BaseAppSettings):
        pass

    monkeypatch.setenv("PAYMENTS_API_KEY", "secret")
    settings = Composed(_env_file=None)
    assert settings.payments_api_key.get_secret_value() == "secret"
    assert "secret" not in repr(settings)
    assert settings.app_name


def test_init_values_win_over_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    assert BaseAppSettings(_env_file=None, log_level="WARNING").log_level == "WARNING"
