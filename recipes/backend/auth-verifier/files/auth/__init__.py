"""Token verifiers for `api/auth.py`: own HS256 JWT, Supabase Auth (JWKS), and the static double.

Chosen in the settings (`AUTH_PROVIDER`), built by `AuthFactory`. Claims become a `CurrentUser`
in one overridable method (`_to_user`), which is where a profile lookup in your DB would go.
"""

from .factory import AuthFactory
from .jwt_verifier import HmacJwtVerifier, JwtVerifier, issue_token
from .models import AuthProvider, TokenClaims
from .settings import AuthSettings
from .supabase import SupabaseJwtVerifier, SupabaseKeys

__all__ = [
    "AuthFactory",
    "AuthProvider",
    "AuthSettings",
    "HmacJwtVerifier",
    "JwtVerifier",
    "SupabaseJwtVerifier",
    "SupabaseKeys",
    "TokenClaims",
    "issue_token",
]
