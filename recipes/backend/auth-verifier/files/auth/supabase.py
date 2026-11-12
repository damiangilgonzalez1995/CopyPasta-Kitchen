"""Tokens issued by Supabase Auth.

Verified with the project's public keys (`<SUPABASE_URL>/auth/v1/.well-known/jwks.json`, ES256 or
RS256), fetched once and kept by `PyJWKClient`. Projects still on the legacy shared secret can set
`SUPABASE_JWT_SECRET` and HS256 tokens are accepted too; without it, a symmetric algorithm is
refused outright (accepting one would let a public key be used as the secret).

Tenant: Supabase has none. The default `_claims` reads `tenant_id` from `app_metadata` (set by you,
server-side) or `user_metadata` (set by the user: only if you trust it), then `AUTH_DEFAULT_TENANT_ID`.
Projects with a profiles table override `_to_user` and look the account up there.
"""

import asyncio
from typing import Any, Protocol

import jwt

from api.auth import AuthUnavailable

from .jwt_verifier import JwtVerifier
from .models import TokenClaims
from .settings import AuthSettings

KEYS_LIFESPAN_SECONDS = 600
KEYS_TIMEOUT_SECONDS = 5
ASYMMETRIC = ["ES256", "RS256"]


class SigningKeys(Protocol):
    def key_for(self, token: str) -> Any:
        """The public key that signed this token. Raises `jwt.PyJWTError` if there is none. May block."""


class SupabaseKeys:
    """The keys Supabase publishes, cached by `PyJWKClient` and refreshed when they expire."""

    def __init__(self, supabase_url: str) -> None:
        self._client = jwt.PyJWKClient(
            f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json",
            lifespan=KEYS_LIFESPAN_SECONDS,
            timeout=KEYS_TIMEOUT_SECONDS,
        )

    def key_for(self, token: str) -> Any:
        return self._client.get_signing_key_from_jwt(token).key


class SupabaseJwtVerifier(JwtVerifier):
    def __init__(self, settings: AuthSettings, keys: SigningKeys | None = None) -> None:
        super().__init__(settings)
        assert settings.supabase_url  # AuthSettings validated it
        self._keys = keys or SupabaseKeys(settings.supabase_url)

    async def _decode(self, token: str) -> dict[str, Any]:
        s = self._settings
        common: dict[str, Any] = dict(
            audience=s.supabase_audience,
            issuer=s.supabase_issuer,
            leeway=s.auth_leeway_seconds,
            options={"require": ["exp", "sub", "iss"]},
        )
        algorithm = jwt.get_unverified_header(token).get("alg")
        if algorithm == "HS256" and s.supabase_jwt_secret is not None:
            return jwt.decode(token, s.supabase_jwt_secret.get_secret_value(), algorithms=["HS256"], **common)
        try:
            key = await asyncio.to_thread(self._keys.key_for, token)  # first time it goes to the network
        except jwt.PyJWKClientConnectionError:
            raise AuthUnavailable("Supabase keys unreachable") from None
        return jwt.decode(token, key, algorithms=ASYMMETRIC, **common)

    def _claims(self, payload: dict[str, Any]) -> TokenClaims:
        app_meta = payload.get("app_metadata") or {}
        user_meta = payload.get("user_metadata") or {}
        return TokenClaims(
            sub=payload["sub"],
            tenant_id=app_meta.get("tenant_id") or user_meta.get("tenant_id"),
            email=payload.get("email"),
            role=app_meta.get("role"),  # `payload["role"]` is "authenticated" for everyone: not a business role
            language=user_meta.get("language"),
        )
