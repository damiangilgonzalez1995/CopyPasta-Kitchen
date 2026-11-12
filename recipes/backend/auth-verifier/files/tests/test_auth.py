"""Verifiers without network: own HS256 tokens, Supabase ES256 tokens signed with a key generated
here (the `SigningKeys` seam replaces the JWKS fetch), and the FastAPI dependency."""

from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends, FastAPI
from pydantic import ValidationError

from api.auth import AuthUnavailable, CurrentUser, InvalidToken, StaticTokenVerifier, get_current_user
from auth import AuthFactory, AuthSettings, HmacJwtVerifier, SupabaseJwtVerifier, issue_token

ALICE = CurrentUser(id="user-1", tenant_id="tenant-1", language="en", email="a@example.com", role="admin")

SECRET = "s3cret-" * 6  # HS256 wants >= 32 bytes


def jwt_settings(**overrides) -> AuthSettings:
    return AuthSettings(**{"auth_provider": "jwt", "jwt_secret": SECRET, "jwt_issuer": "{{app_name}}", **overrides})


JWT_SETTINGS = jwt_settings()


def hs256(payload: dict, secret: str = SECRET) -> str:
    return jwt.encode(payload, secret, algorithm="HS256")


# --- Own JWT (HS256) -------------------------------------------------------------------------


async def test_issued_token_round_trips_to_the_same_user():
    token = issue_token(JWT_SETTINGS, ALICE, ttl_seconds=60)
    assert await HmacJwtVerifier(JWT_SETTINGS).verify(token) == ALICE


async def test_expired_forged_or_wrong_issuer_tokens_are_invalid():
    verifier = HmacJwtVerifier(JWT_SETTINGS)
    past = datetime.now(UTC) - timedelta(hours=1)
    cases = {
        "expired": issue_token(JWT_SETTINGS, ALICE, now=past, ttl_seconds=60),
        "forged": issue_token(jwt_settings(jwt_secret="other-" * 6), ALICE),
        "issuer": hs256({"sub": "u", "tenant_id": "t", "iss": "someone-else", "exp": 4102444800}),
        "no sub": hs256({"tenant_id": "t", "iss": "{{app_name}}", "exp": 4102444800}),
        "no exp": hs256({"sub": "u", "tenant_id": "t", "iss": "{{app_name}}"}),
        "garbage": "not.a.token",
    }
    for name, token in cases.items():
        with pytest.raises(InvalidToken):
            await verifier.verify(token)
        print("refused:", name)


async def test_tenant_comes_from_the_claim_then_the_default_then_refused():
    settings = jwt_settings(jwt_issuer=None)
    token = hs256({"sub": "u", "exp": 4102444800})

    with pytest.raises(InvalidToken, match="tenant"):
        await HmacJwtVerifier(settings).verify(token)
    with_default = jwt_settings(jwt_issuer=None, auth_default_tenant_id="default")
    assert (await HmacJwtVerifier(with_default).verify(token)).tenant_id == "default"
    user = await HmacJwtVerifier(with_default).verify(hs256({"sub": "u", "tenant_id": "mine", "exp": 4102444800}))
    assert (user.tenant_id, user.language) == ("mine", "es")


async def test_audience_is_checked_only_when_configured():
    settings = jwt_settings(jwt_audience="api")
    assert (await HmacJwtVerifier(settings).verify(issue_token(settings, ALICE))).id == "user-1"
    with pytest.raises(InvalidToken):
        await HmacJwtVerifier(settings).verify(issue_token(JWT_SETTINGS, ALICE))  # no aud claim


# --- Supabase (ES256 via JWKS, HS256 legacy) --------------------------------------------------


class FakeKeys:
    """Stands in for the JWKS endpoint: always the same public key, or a connection error."""

    def __init__(self, public_key=None, *, down: bool = False) -> None:
        self.public_key, self.down = public_key, down

    def key_for(self, token: str):
        if self.down:
            raise jwt.PyJWKClientConnectionError("boom")
        return self.public_key


@pytest.fixture
def supabase():
    private = ec.generate_private_key(ec.SECP256R1())
    settings = AuthSettings(auth_provider="supabase", supabase_url="https://xyz.supabase.co/")
    return settings, SupabaseJwtVerifier(settings, keys=FakeKeys(private.public_key())), private


def supabase_payload(**extra) -> dict:
    return {
        "sub": "uuid-1",
        "aud": "authenticated",
        "iss": "https://xyz.supabase.co/auth/v1",
        "role": "authenticated",
        "email": "a@example.com",
        "exp": 4102444800,
        **extra,
    }


async def test_supabase_token_maps_tenant_and_role_from_app_metadata(supabase):
    settings, verifier, private = supabase
    token = jwt.encode(
        supabase_payload(app_metadata={"tenant_id": "acme", "role": "manager"}, user_metadata={"language": "fr"}),
        private,
        algorithm="ES256",
    )

    user = await verifier.verify(token)

    assert user == CurrentUser(id="uuid-1", tenant_id="acme", language="fr", email="a@example.com", role="manager")


async def test_supabase_refuses_other_audience_issuer_or_key(supabase):
    settings, verifier, private = supabase
    other = ec.generate_private_key(ec.SECP256R1())
    cases = {
        "audience": jwt.encode(supabase_payload(aud="anon"), private, algorithm="ES256"),
        "issuer": jwt.encode(supabase_payload(iss="https://evil.example/auth/v1"), private, algorithm="ES256"),
        "other key": jwt.encode(supabase_payload(), other, algorithm="ES256"),
        "hs256 without legacy secret": hs256(supabase_payload(app_metadata={"tenant_id": "t"})),
        "no tenant anywhere": jwt.encode(supabase_payload(), private, algorithm="ES256"),
    }
    for name, token in cases.items():
        with pytest.raises(InvalidToken):
            await verifier.verify(token)
        print("refused:", name)


async def test_supabase_legacy_hs256_secret_is_accepted_when_configured():
    settings = AuthSettings(
        auth_provider="supabase", supabase_url="https://xyz.supabase.co", supabase_jwt_secret="legacy-" * 6, auth_default_tenant_id="t"
    )
    verifier = SupabaseJwtVerifier(settings, keys=FakeKeys(down=True))  # never consulted for HS256

    user = await verifier.verify(hs256(supabase_payload(), "legacy-" * 6))

    assert (user.id, user.tenant_id) == ("uuid-1", "t")


async def test_supabase_keys_unreachable_is_unavailable_not_invalid(supabase):
    settings, _, private = supabase
    verifier = SupabaseJwtVerifier(settings, keys=FakeKeys(down=True))
    with pytest.raises(AuthUnavailable):
        await verifier.verify(jwt.encode(supabase_payload(), private, algorithm="ES256"))


async def test_profile_lookup_is_one_method():
    class WithProfiles(HmacJwtVerifier):
        profiles = {"user-1": ("tenant-9", "editor")}

        async def _to_user(self, claims, payload):  # e.g. a DB query
            try:
                tenant_id, role = self.profiles[claims.sub]
            except KeyError:
                raise InvalidToken("no profile") from None
            return CurrentUser(id=claims.sub, tenant_id=tenant_id, role=role)

    verifier = WithProfiles(JWT_SETTINGS)
    assert (await verifier.verify(issue_token(JWT_SETTINGS, ALICE))).tenant_id == "tenant-9"
    with pytest.raises(InvalidToken):
        await verifier.verify(issue_token(JWT_SETTINGS, ALICE.model_copy(update={"id": "nobody"})))


# --- Settings + factory: the provider is chosen in .env, not in code -------------------------


def test_provider_comes_from_env_and_each_one_needs_its_keys(monkeypatch):
    monkeypatch.setenv("AUTH_PROVIDER", "jwt")
    monkeypatch.setenv("JWT_SECRET", SECRET)
    assert isinstance(AuthFactory.create(AuthSettings()), HmacJwtVerifier)

    monkeypatch.delenv("JWT_SECRET")
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        AuthSettings()
    with pytest.raises(ValidationError, match="SUPABASE_URL"):
        AuthSettings(auth_provider="supabase")
    monkeypatch.delenv("AUTH_PROVIDER")
    with pytest.raises(ValidationError):
        AuthSettings()
    with pytest.raises(ValidationError):
        AuthSettings(auth_provider="ldap")


def test_static_provider_needs_users_given_in_code():
    settings = AuthSettings(auth_provider="static")
    with pytest.raises(ValueError, match="static_users"):
        AuthFactory.create(settings)
    assert isinstance(AuthFactory.create(settings, static_users={"tok": ALICE}), StaticTokenVerifier)
    assert isinstance(
        AuthFactory.create(AuthSettings(auth_provider="supabase", supabase_url="https://x.supabase.co")), SupabaseJwtVerifier
    )


def test_secrets_never_show_in_repr():
    assert SECRET not in repr(JWT_SETTINGS) and SECRET not in str(JWT_SETTINGS)


# --- The dependency: 401 vs 503 ---------------------------------------------------------------


async def test_dependency_maps_invalid_to_401_and_unavailable_to_503():
    app = FastAPI()

    @app.get("/me")
    async def me(user: CurrentUser = Depends(get_current_user)) -> dict:
        return {"id": user.id}

    token = issue_token(JWT_SETTINGS, ALICE)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        app.state.token_verifier = HmacJwtVerifier(JWT_SETTINGS)
        assert (await c.get("/me", headers={"Authorization": f"Bearer {token}"})).json() == {"id": "user-1"}
        refused = await c.get("/me", headers={"Authorization": "Bearer nope"})
        assert refused.status_code == 401 and refused.headers["www-authenticate"] == "Bearer"
        assert (await c.get("/me")).status_code == 401

        down = AuthSettings(auth_provider="supabase", supabase_url="https://x.supabase.co")
        app.state.token_verifier = SupabaseJwtVerifier(down, keys=FakeKeys(down=True))
        es_token = jwt.encode(supabase_payload(), ec.generate_private_key(ec.SECP256R1()), algorithm="ES256")
        assert (await c.get("/me", headers={"Authorization": f"Bearer {es_token}"})).status_code == 503
