# fastapi-base

## Cuándo usarla

Para **arrancar cualquier backend FastAPI** con la fontanería que todos los proyectos acaban teniendo: id de petición en cada respuesta y en cada línea de log, fallos inesperados como 500 sin internals, un formato de error con `code`, CORS desde settings, `/health` y `/docs` solo cuando se pide. Es la base sobre la que `agent-chat-api` monta el chat.

No depende de otras recetas. **Usa `project-settings`** (bloque `ApiSettings`).

## Qué incluye

```
api/
  base.py           build_app(title, lifespan, docs, cors_origins): FastAPI + request id + CORS + /health
  app.py            create_app(settings): plantilla del create_app del proyecto (agent-chat-api la sustituye)
  request_id.py     X-Request-ID (del cliente si es sano, si no uuid), contextvar, RequestIdFilter, 500 sin internals
  errors.py         ApiError(status, code, **extra) → {"detail": {"code": ..., ...}} · ErrorDetail
  logging_setup.py  configure_logging(level): formato con [request_id], uvicorn.access y httpx silenciados
  health.py         GET /health {status: ok} sin auth ni dependencias
  settings.py       bloque ApiSettings: CORS_ORIGINS (coma), DOCS_ENABLED
tests/test_api_base.py   11 tests: health, request id propio y del cliente, 500 sin fuga, ApiError, CORS, docs, settings, logging
pytest.ini
```

## Decisiones

- **`build_app` y `create_app` separados.** `build_app` es la fontanería, igual en todos los proyectos; `create_app` es del proyecto: servicios en `app.state`, lifespan, routers. Las recetas que montan algo encima (`agent-chat-api`) traen su `create_app` y llaman a `build_app`. Nada lee el entorno: todo se inyecta (Vera).
- **El cuerpo de error sigue siendo `{"detail": ...}`.** Vera usa un sobre propio `{error: {code, message, request_id}}`, pero los frontends de aurora y ATI (y `react-agent-chat`) leen `detail`, y FastAPI ya lo produce para 401, 404 y 422. La convención es: cuando el cliente tiene que distinguir casos, `detail` es un objeto con `code` (`ApiError`); si no, una cadena. Los 500 inesperados son `{"detail": {"code": "internal_error", "request_id"}}`.
- **El id de la petición lo pone el cliente si quiere** (ATI): se respeta `X-Request-ID` si es `[A-Za-z0-9._-]{1,64}`; si no, se genera. Va en `request.state`, en un contextvar para los logs y en la respuesta, también en los errores y en CORS (`expose_headers`).
- **500 sin internals, con el mismo id en el log** (Vera). El middleware captura lo que nadie manejó, hace `logger.exception` y responde con `code` e id. El cliente nunca ve el traceback; soporte cruza el id con el log.
- **CORS solo si hay orígenes** y añadido primero para que quede el más externo: el preflight se responde antes de pasar por nada (ATI). `allow_credentials=True` con lista explícita, nunca `*`.
- **`/health` sin dependencias.** Es liveness. Un readiness que toque la base de datos es otra ruta con sus timeouts; si no, la API cae con la base de datos.
- **`/docs` y `/openapi.json` apagados por defecto** (ATI, Vera): publican el mapa completo de la API. `DOCS_ENABLED=true` en local.
- **`logging` estándar con el id en el formato.** Un solo sitio (`configure_logging`) para cambiar a JSON o structlog cuando haya colector.

## Cómo adaptarla

1. Copia `files/` en la raíz del backend. Sustituye `{{app_name}}` en `api/app.py`.
2. **Settings:** `class Settings(ApiSettings, BaseAppSettings)`. En el `.env`: `CORS_ORIGINS=http://localhost:5173` y, en local, `DOCS_ENABLED=true`.
3. **`main.py`:**

   ```python
   settings = get_settings()
   configure_logging(settings.log_level)
   app = create_app(settings=settings)
   ```

   `uvicorn main:app`. Añade tus routers en `create_app` con `app.include_router(...)`.
4. **Errores con código:** `raise ApiError(409, "inventory_closed", closed_at=...)`. Para un 404 corriente, `HTTPException(404, "Not Found")` sigue valiendo.
5. **Excepciones de dominio:** `app.add_exception_handler(MyDomainError, handler)` en `create_app`, devolviendo `JSONResponse({"detail": {"code": ...}})`; el middleware añadirá el id.
6. Para comprobarla: `pytest` en solitario (11 tests) o con las recetas backend (`agent-chat-api` y las demás: 158 con las diez).

**Dependencias:** `fastapi`, `pydantic-settings>=2.7` (`NoDecode`); `httpx` en tests.

## Origen

- Middleware que etiqueta la petición con `request_id`, lo pone en el log y convierte cualquier fallo en un JSON sin internals; `create_app(settings)` con servicios en `app.state`; `/docs` solo en local; `/health` sin dependencias: Vera-Symplia (`api/error_handlers.py`, `api/app.py`, `routers/health.py`).
- `X-Request-ID` del cliente respetado y devuelto, CORS antes del resto de middlewares, docs apagados fuera de desarrollo: ATI_PLATFORM (`api/middlewares/request_context.py`, `main.py`).
- `CORS_ALLOWED_ORIGINS` separado por comas desde settings: aurora (`api/main.py`).
- `detail` con `code` como formato único (en vez del sobre `{error: ...}` de Vera) y `ApiError`: nuevos, para conservar el contrato que ya leen los frontends.
