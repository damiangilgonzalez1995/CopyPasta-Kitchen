"""Auth settings BLOCK, meant to be mixed into the project settings (`project-settings` recipe):

    class Settings(AuthSettings, BaseAppSettings): ...

Env vars: AUTH_PROVIDER (required: static | jwt | supabase), AUTH_DEFAULT_TENANT_ID (tokens without a
tenant claim get it; empty = such tokens are refused), AUTH_LEEWAY_SECONDS (30).
JWT: JWT_SECRET (required), JWT_ISSUER, JWT_AUDIENCE, JWT_TTL_SECONDS (for `issue_token`, 7 days).
SUPABASE: SUPABASE_URL (required), SUPABASE_AUDIENCE (authenticated), SUPABASE_JWT_SECRET (only for
projects still on the legacy HS256 secret; empty = asymmetric keys only).
"""

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import AuthProvider


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # No default on purpose: falling back to the static double would ship an open door.
    auth_provider: AuthProvider
    auth_default_tenant_id: str | None = Field(default=None, min_length=1)
    auth_leeway_seconds: int = Field(default=30, ge=0, description="Clock skew tolerated on exp/nbf/iat.")

    jwt_secret: SecretStr | None = None
    jwt_issuer: str | None = None
    jwt_audience: str | None = None
    jwt_ttl_seconds: int = Field(default=7 * 24 * 3600, ge=1)

    supabase_url: str | None = None
    supabase_audience: str = "authenticated"
    supabase_jwt_secret: SecretStr | None = None

    @model_validator(mode="after")
    def _provider_has_what_it_needs(self) -> "AuthSettings":
        if self.auth_provider == AuthProvider.JWT and self.jwt_secret is None:
            raise ValueError("AUTH_PROVIDER=jwt needs JWT_SECRET")
        if self.auth_provider == AuthProvider.SUPABASE and not self.supabase_url:
            raise ValueError("AUTH_PROVIDER=supabase needs SUPABASE_URL")
        return self

    @property
    def supabase_issuer(self) -> str:
        return f"{(self.supabase_url or '').rstrip('/')}/auth/v1"
