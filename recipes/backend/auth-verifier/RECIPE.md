# auth-verifier

## Cuándo usarla

Para **saber quién llama** a partir de un token Bearer sin atar la API a un proveedor: Supabase Auth (claves públicas por JWKS), JWT propio con secreto compartido, o un doble estático para tests. El proveedor se elige en `.env` y la API solo conoce `TokenVerifier.verify(token) -> CurrentUser`.

No depende de otras recetas: trae su propio `api/auth.py` (el mismo archivo que `agent-chat-api`; copiar encima no cambia nada). **Usa `project-settings`** (bloque `AuthSettings`).

## Qué incluye

```
api/auth.py           CurrentUser · InvalidToken (401) · AuthUnavailable (503) · TokenVerifier (ABC) · StaticTokenVerifier · get_current_user
auth/
  models.py           AuthProvider (static | jwt | supabase) · TokenClaims
  settings.py         bloque AuthSettings: AUTH_PROVIDER (obligatorio), AUTH_DEFAULT_TENANT_ID, JWT_*, SUPABASE_*
  jwt_verifier.py     JwtVerifier (decodificar → claims → CurrentUser, con `_to_user` sobrescribible) · HmacJwtVerifier · issue_token
  supabase.py         SupabaseJwtVerifier (ES256/RS256 por JWKS, HS256 legado opcional) · SupabaseKeys · SigningKeys (costura)
  factory.py          AuthFactory.create(settings, static_users=...)
tests/test_auth.py    13 tests sin red: HS256, caducidad, emisor, audiencia, tenant, Supabase ES256 con clave generada, legado, 503, factory
pytest.ini
```

## Decisiones

- **Un contrato, tres proveedores.** `TokenVerifier` vive en `app.state.token_verifier` (Vera) y `AuthFactory` construye el que diga `AUTH_PROVIDER`, sin valor por defecto: caer en el doble estático sería dejar una puerta abierta. El estático exige los usuarios en código, nunca del entorno.
- **Claims → usuario en un solo método.** `JwtVerifier._to_user` convierte las claims en `CurrentUser`; es async para que un proyecto con tabla de perfiles (ATI, Vera) la consulte ahí y rechace cuentas sin perfil. `_claims` dice dónde están los campos: Supabase los lleva en `app_metadata` (puesto por el servidor, fiable) o `user_metadata` (lo pone el usuario: solo si te fías).
- **Tenant obligatorio.** Sin claim de tenant ni `AUTH_DEFAULT_TENANT_ID`, el token se rechaza: una conversación sin tenant no tiene espacio donde vivir.
- **Supabase solo con claves asimétricas** (ES256/RS256 por JWKS, como Vera), con `aud=authenticated` e `iss=<SUPABASE_URL>/auth/v1`. Aceptar HS256 sin más permitiría usar la clave pública como secreto; se admite solo si configuras `SUPABASE_JWT_SECRET` (proyectos aún con el secreto legado, como ATI).
- **JWKS caído no es 401.** `AuthUnavailable` se traduce a 503: el cliente no debe cerrar la sesión porque el proveedor no conteste (ATI lo sufrió con 401). La primera obtención de claves va en `asyncio.to_thread`.
- **Los motivos solo al log.** Todo fallo de PyJWT es `InvalidToken` y el cliente ve "Invalid token"; el detalle (caducado, emisor, firma) queda en el log a nivel info.
- **`SigningKeys` es la costura de test:** los tests firman con una clave ES256 generada al vuelo y la inyectan en lugar del JWKS. Sin red.
- **`issue_token` solo para el proveedor JWT:** para tu endpoint de login o un script de desarrollo. Con Supabase los tokens los da Supabase.
- **Tolerancia de reloj** (`AUTH_LEEWAY_SECONDS=30`) como ATI: sin ella un desfase de segundos expulsa al usuario nada más entrar.

## Cómo adaptarla

1. Copia `files/` en la raíz del backend (encima de `agent-chat-api` si la usas).
2. **Settings:** `class Settings(AuthSettings, BaseAppSettings)`. En el `.env`, uno de:

   ```
   AUTH_PROVIDER=supabase
   SUPABASE_URL=https://xyz.supabase.co
   # SUPABASE_JWT_SECRET=...        solo proyectos con el secreto HS256 legado
   AUTH_DEFAULT_TENANT_ID=default   # o pon tenant_id en app_metadata
   ```

   ```
   AUTH_PROVIDER=jwt
   JWT_SECRET=<32 bytes o más>
   JWT_ISSUER={{app_name}}
   ```

3. **`main.py`:** `create_app(token_verifier=AuthFactory.create(settings), ...)`. En tests, `AuthFactory.create(settings, static_users={...})` o `StaticTokenVerifier` directamente.
4. **Perfiles en tu base de datos:** subclase de `HmacJwtVerifier` o `SupabaseJwtVerifier` que sobrescriba `_to_user(claims, payload)` y busque el perfil (ver `test_profile_lookup_is_one_method`). Añade la rama en `AuthFactory`.
5. **Roles:** `CurrentUser.role` llega de la claim (`app_metadata.role` en Supabase). Las comprobaciones (403) van en `ensure_turn_allowed` o en una dependencia `require_roles`, no aquí.
6. Para comprobarla: `pytest` en solitario (13 tests) o con las recetas backend (147 con las nueve).

**Dependencias:** `pyjwt[crypto]` (incluye `cryptography`, necesaria para ES256), `pydantic-settings`, `fastapi`; `httpx` en tests. Probado con PyJWT 2.15.

## Origen

- Proveedor elegido por settings (`AUTH_PROVIDER=local | supabase`), JWT propio HS256 con `sub`, `tenant_id` y caducidad, `create_token` para el login local, tenant por defecto desde settings y metadatos de usuario de Supabase: aurora (`api/auth/auth.py`).
- JWKS de Supabase con ES256 y HS256 legado según la cabecera del token, `leeway` de 30 s, `role=authenticated` como señal de usuario no anónimo, búsqueda del perfil tras verificar: ATI_PLATFORM (`core/security.py`, `api/deps.py`).
- `TokenVerifier` en `app.state`, `PyJWKClient` con caché e inyectable (`SigningKeys`), solo algoritmos asimétricos, `audience` e `issuer` verificados, error distinto cuando el proveedor no responde, factory sin valor por defecto y doble de test: Vera-Symplia (`auth/base.py`, `auth/supabase.py`, `auth/factory.py`, `auth/test_double.py`).
- `_to_user` como único punto de mapeo y `TokenClaims` como modelo intermedio: nuevos, para que cambiar de proveedor o añadir la tabla de perfiles no toque el resto.
