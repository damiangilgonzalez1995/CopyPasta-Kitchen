# agent-chat-api

## Cuándo usarla

Para **exponer el agente por HTTP**: el endpoint de chat que consume la interfaz (`react-agent-chat`) o cualquier cliente. Dos rutas sobre el mismo turno: `POST /agent/chat` devuelve JSON y `POST /agent/stream` devuelve SSE.

**Requiere `langgraph-graph`** (y con ella `langchain-agent` y `agent-memory`): el router llama a `answer_question` y `stream_answer`. Usa `project-settings` para el bloque `AgentApiSettings`. La auth y las cuotas tienen aquí su costura; las recetas `auth-verifier` y `rate-limit-quota` (pendientes) la rellenan.

## Qué incluye

```
api/
  app.py                create_app(settings, token_verifier, memory, document_search): FastAPI + lifespan
  auth.py               CurrentUser · TokenVerifier (ABC) · StaticTokenVerifier (tests) · get_current_user
  agent/
    router.py           POST /agent/chat (JSON) · POST /agent/stream (SSE) · Turn (clave + contexto)
    schemas.py          ChatRequest{question, conversation_id?, language?} · ChatResponse{answer, conversation_id, message_id}
    guards.py           require_agent_enabled (404) · ensure_turn_allowed (403/429: punto de extensión)
    sanitize.py         sanitize_question: trim, longitud, caracteres de control, etiquetas HTML → 400
    settings.py         AgentApiSettings: AGENT_ENDPOINT_ENABLED, CHAT_MAX_QUESTION_LENGTH
tests/test_agent_api.py 10 tests: 401, 404 con el flag, 400, ids, aislamiento por tenant, guard 429, SSE, error sin detalle, idioma
pytest.ini
```

## Decisiones

- **El mismo turno, dos respuestas.** Las dos rutas construyen el mismo `Turn` (pregunta limpia, `MemoryKey`, `AgentContext`) y solo cambia cómo se entrega. Aurora y ATI lo hacen así.
- **Los tres ids.** El cliente solo elige `conversation_id` (y si no lo manda, lo genera el servidor con `uuid4`). `tenant_id` y `user_id` salen del token. Pedir el `conversation_id` de otro no abre su hilo.
- **Guards en orden y antes de abrir el stream:** flag apagado → 404 (que no se note que hay algo detrás), sin token → 401, `ensure_turn_allowed` → 403 o 429, pregunta vacía → 400. Una vez enviado el primer byte del SSE ya no se puede cambiar el status.
- **`ensure_turn_allowed` es el punto de extensión** para rol, cuota y rate limit. Por defecto deja pasar. Se sustituye con `app.dependency_overrides` o editándolo. Nada que bloquee dentro de él sin `run_in_threadpool`.
- **La auth es una clase base.** `TokenVerifier.verify(token) -> CurrentUser` vive en `app.state`, así que el proveedor se decide al construir la app y los tests usan `StaticTokenVerifier`. `auth-verifier` traerá Supabase y JWT propio con su factory.
- **`done` lleva `conversation_id` y `message_id`.** `message_id` es la respuesta guardada en `agent-memory`: lo que el cliente manda al votar (futura `agent-feedback`). `ChatResponse` tiene los mismos campos.
- **Persistir antes de responder.** `answer_question` y `stream_answer` escriben en memoria antes de devolver o de emitir `done`. En background abriría una carrera con varios workers (ATI lo sufrió).
- **Errores en el stream sin detalle.** El grafo ya convierte sus fallos en `error{error_id}`; el router hace lo mismo con lo que falle fuera del grafo (memoria, red). El detalle solo va al log, con el `error_id` y el `thread_id`.
- **`create_app` con todo inyectado.** No lee el entorno: `main.py` construye las piezas desde el `Settings` del proyecto y las pasa. `/docs` oculto salvo `docs=True`.
- **Sin imágenes ni adjuntos.** Aurora y ATI mandan imágenes en base64 dentro del body; es una extensión de `ChatRequest` y de `AgentContext`, no de esta receta.

## Cómo adaptarla

1. Copia `files/` al backend, encima de las recetas requeridas. Sustituye `{{app_name}}` en `api/app.py`.
2. **Settings:** añade `AgentApiSettings` a la herencia de tu `Settings` (`core/config.py`). Variables: `AGENT_ENDPOINT_ENABLED=true`, `CHAT_MAX_QUESTION_LENGTH=4000`.
3. **Auth:** escribe un `TokenVerifier` para tu proveedor (o copia `auth-verifier` cuando exista) y pásalo a `create_app`.
4. **`main.py`:**

   ```python
   settings = get_settings()
   app = create_app(
       settings=settings,
       token_verifier=MyVerifier(settings),
       memory=MemoryFactory.create(settings, session_factory=SessionLocal),
       document_search=my_search_service,
   )
   ```

5. **Cuota o rate limit:** implementa `ensure_turn_allowed` (403 o 429 con `detail={"code": ...}`; el frontend de ATI lee `code` y `resets_at`).
6. **Más rutas** (historial, feedback): un router por grupo en `api/<grupo>/router.py`, con `get_current_user` como dependencia.
7. Para comprobarla: `pytest` con las cuatro recetas backend copiadas (66 tests en total).

**Dependencias** (además de las de `langgraph-graph`): `fastapi`, `sse-starlette`, `httpx` (tests). Probado con fastapi 0.162.5 y sse-starlette 3.7.0.

## Origen

- Dos rutas (JSON y SSE) sobre el mismo grafo, `conversation_id` del cliente con `uuid4` del servidor si falta, tenant y usuario del token, guards antes del stream (flag 404 → acceso 403 → cuota → rate limit → saneado 400), `done` con `conversation_id` y `message_id`, persistir antes de responder, `error_id` en el stream: ATI_PLATFORM (`api/routes/agent.py`, `schemas/agent_schema.py`, `services/input_sanitizer.py`).
- `EventSourceResponse` de sse-starlette, `session_id` del cliente y rate limit como dependencia que devuelve el usuario: aurora (`api/routers/chat.py`).
- `create_app(settings)` con los servicios en `app.state`, verificador de tokens como objeto en `app.state`, `/docs` solo en desarrollo: Vera-Symplia (`api/app.py`, `auth/roles.py`).
- `TokenVerifier` como clase base con doble estático y `ensure_turn_allowed` como dependencia sustituible: nuevos, para mantener la auth y las cuotas fuera de esta receta.
