"""The one place that builds the verifier the settings name. There is no default."""

from api.auth import CurrentUser, StaticTokenVerifier, TokenVerifier

from .models import AuthProvider
from .settings import AuthSettings


class AuthFactory:
    @staticmethod
    def create(settings: AuthSettings, *, static_users: dict[str, CurrentUser] | None = None) -> TokenVerifier:
        """Once at startup:
            app = create_app(token_verifier=AuthFactory.create(get_settings()), ...)
        `STATIC` needs `static_users` (built in code: never from the environment)."""
        match settings.auth_provider:
            case AuthProvider.STATIC:
                if static_users is None:
                    raise ValueError("AUTH_PROVIDER=static needs static_users (tests and local dev only)")
                return StaticTokenVerifier(static_users)
            case AuthProvider.JWT:
                from .jwt_verifier import HmacJwtVerifier

                return HmacJwtVerifier(settings)
            case AuthProvider.SUPABASE:
                from .supabase import SupabaseJwtVerifier

                return SupabaseJwtVerifier(settings)
        raise ValueError(f"Unknown auth provider: {settings.auth_provider!r}")
