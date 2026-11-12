"""Who is calling: `CurrentUser` from a Bearer token.

The router never parses tokens itself. It asks the `TokenVerifier` stored in `app.state`, so the
provider (Supabase, own JWT, API key...) is chosen when the app is built, and tests use
`StaticTokenVerifier`. The `auth-verifier` recipe provides the real verifiers and their factory;
until then, write one subclass here.
"""

from abc import ABC, abstractmethod

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field


class CurrentUser(BaseModel):
    """The authenticated caller. `tenant_id` and `id` are the namespace of every conversation,
    so they come from the token and never from the request body. Add role, email... as needed."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    language: str = Field(default="es", description="Fallback language when the request has none.")


class InvalidToken(Exception):
    """The token is missing, expired, forged or belongs to nobody. Reason only for the logs."""


class TokenVerifier(ABC):
    @abstractmethod
    async def verify(self, token: str) -> CurrentUser:
        """Return the caller or raise `InvalidToken`."""


class StaticTokenVerifier(TokenVerifier):
    """A fixed `token -> user` table. For tests and local development only."""

    def __init__(self, users: dict[str, CurrentUser]) -> None:
        self._users = users

    async def verify(self, token: str) -> CurrentUser:
        try:
            return self._users[token]
        except KeyError:
            raise InvalidToken("unknown token") from None


# auto_error=False: a missing header gets the same 401 as a bad token, with our own message.
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)
) -> CurrentUser:
    verifier: TokenVerifier | None = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        raise RuntimeError("app.state.token_verifier is not set: build the app with a TokenVerifier")
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", {"WWW-Authenticate": "Bearer"})
    try:
        return await verifier.verify(credentials.credentials)
    except InvalidToken:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token", {"WWW-Authenticate": "Bearer"}) from None
