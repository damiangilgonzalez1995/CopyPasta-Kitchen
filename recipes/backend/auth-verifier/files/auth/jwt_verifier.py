"""JWT verification shared by every JWT-based provider, and the own-secret (HS256) verifier.

    JwtVerifier       decode (subclass: `_decode`) -> TokenClaims -> CurrentUser (`_to_user`, overridable)
    HmacJwtVerifier   tokens this backend issued with `JWT_SECRET` (see `issue_token`)

All PyJWT errors become `InvalidToken`: the reason goes to the log, never to the client.
"""

import logging
from abc import abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from api.auth import CurrentUser, InvalidToken, TokenVerifier

from .models import TokenClaims
from .settings import AuthSettings

logger = logging.getLogger(__name__)


class JwtVerifier(TokenVerifier):
    def __init__(self, settings: AuthSettings) -> None:
        self._settings = settings

    async def verify(self, token: str) -> CurrentUser:
        try:
            payload = await self._decode(token)
        except jwt.PyJWTError as exc:
            logger.info("Token refused: %s", exc)
            raise InvalidToken(str(exc)) from None
        claims = self._claims(payload)
        return await self._to_user(claims, payload)

    @abstractmethod
    async def _decode(self, token: str) -> dict[str, Any]:
        """Verify signature, expiry, issuer/audience and required claims. Raise `jwt.PyJWTError`."""

    def _claims(self, payload: dict[str, Any]) -> TokenClaims:
        """Which payload fields matter. Override when your provider stores them elsewhere."""
        return TokenClaims(**payload)

    async def _to_user(self, claims: TokenClaims, payload: dict[str, Any]) -> CurrentUser:
        """Claims -> caller. Async so a subclass can look the profile up in the DB (then raise
        `InvalidToken` for an account without profile). Default: tenant from the claim or
        `AUTH_DEFAULT_TENANT_ID`; no tenant at all -> refused."""
        tenant_id = claims.tenant_id or self._settings.auth_default_tenant_id
        if not tenant_id:
            raise InvalidToken("token without tenant and no AUTH_DEFAULT_TENANT_ID")
        return CurrentUser(
            id=claims.sub,
            tenant_id=tenant_id,
            email=claims.email,
            role=claims.role,
            **({"language": claims.language} if claims.language else {}),
        )


class HmacJwtVerifier(JwtVerifier):
    """Tokens signed by this backend with the shared `JWT_SECRET` (HS256)."""

    ALGORITHMS = ["HS256"]

    async def _decode(self, token: str) -> dict[str, Any]:
        s = self._settings
        assert s.jwt_secret is not None  # AuthSettings validated it
        return jwt.decode(
            token,
            s.jwt_secret.get_secret_value(),
            algorithms=self.ALGORITHMS,
            issuer=s.jwt_issuer,
            audience=s.jwt_audience,
            leeway=s.auth_leeway_seconds,
            options={"require": ["exp", "sub"], "verify_aud": s.jwt_audience is not None},
        )


def issue_token(settings: AuthSettings, user: CurrentUser, *, ttl_seconds: int | None = None, now: datetime | None = None) -> str:
    """A token `HmacJwtVerifier` accepts, for your login endpoint or a dev script.
    Only the JWT provider issues tokens: with Supabase the frontend gets them from Supabase."""
    if settings.jwt_secret is None:
        raise ValueError("issue_token needs JWT_SECRET")
    now = now or datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": user.id,
        "tenant_id": user.tenant_id,
        "language": user.language,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds or settings.jwt_ttl_seconds)).timestamp()),
    }
    if user.email:
        payload["email"] = user.email
    if user.role:
        payload["role"] = user.role
    if settings.jwt_issuer:
        payload["iss"] = settings.jwt_issuer
    if settings.jwt_audience:
        payload["aud"] = settings.jwt_audience
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")
