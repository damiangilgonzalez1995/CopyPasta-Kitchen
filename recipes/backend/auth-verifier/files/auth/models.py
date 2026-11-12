from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AuthProvider(StrEnum):
    """Who signs the tokens. Chosen in the settings (`AUTH_PROVIDER`), built by `AuthFactory`.

    STATIC: a fixed token -> user table given in code (tests, local dev). Never in production.
    JWT: tokens the backend issues itself with a shared secret (HS256). Own login endpoint.
    SUPABASE: tokens issued by Supabase Auth, verified with its public keys (JWKS).
    """

    STATIC = "static"
    JWT = "jwt"
    SUPABASE = "supabase"


class TokenClaims(BaseModel):
    """The claims a verifier cares about, already validated. `tenant_id` may still be missing
    here: `JwtVerifier._to_user` decides what to do with that."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    sub: str = Field(min_length=1)
    tenant_id: str | None = None
    email: str | None = None
    role: str | None = None
    language: str | None = None
