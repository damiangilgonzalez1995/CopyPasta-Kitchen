# Chat conversacional con IA: patrones de punta a punta

Síntesis de cómo está hecho el chat con IA en aurora, ATI_PLATFORM, Vera-Symplia y rag_tool_upv, y qué cubren ya las recetas. Complementa `agentic-langgraph.md` (grafo y streaming) y `frontend.md` (SPA y cliente HTTP).

## Cómo lo hace cada proyecto

| Pieza | aurora | ATI_PLATFORM | Vera-Symplia | rag_tool_upv |
|---|---|---|---|---|
| Endpoints de chat | `POST /chat/invoke` (JSON) y `/chat/invoke/stream` (SSE, sse-starlette) | `POST /api/agent/chat` (JSON) y `/api/agent/stream` (SSE, sse-starlette) | Jobs con polling: `POST /jobs`, `GET /jobs/{id}`; sin SSE | No hay backend de chat; vive en n8n |
| Request | `ChatRequest{message, session_id?, image_base64?, mime_type_img?}` | `AgentChatRequest{question, conversation_id?, images[]?, language?}` | `JobCreate{client_id, text, ...}` | — |
| Id de conversación | Cliente, `uuid4` del servidor si falta; `thread_id = tenant_user_session` | Cliente, `uuid4` del servidor si falta; `MemoryKey(company, user, conversation)` frozen | Servidor (`job_id`, `session_id`) + `client_id` de idempotencia | `sessionId` del widget en localStorage |
| Tenant y usuario | JWT (local o Supabase `get_user`), tenant en `user_metadata` | JWT Supabase + `Profile`/`Membership` en BD | `TokenVerifier` → `Identity{id, name, role}`, sin tenant | API key compartida |
| Persistencia | Qdrant vía MCP, en background | Postgres `agent_messages`, síncrona antes de `done` | Postgres solo inserción (`session_conversation`, `job_messages`) | Data Table de n8n |
| Listar conversaciones | `GET /conversations`, `GET /conversations/{id}/messages` | Solo auditoría de admin (`/api/agent-audit`) | `GET /sessions`, `/sessions/{id}/conversation`, `/admin/conversations` | No |
| Borrar / renombrar | No (borrado solo local en el front) | No | No (tablas de solo inserción) | No |
| Feedback | No | `POST /api/agent/feedback {message_id, rating ±1}`, UPSERT, `UNIQUE(message, user)` | No | No |
| Rate limit (429) | Ventana deslizante en memoria por usuario | Redis Lua o memoria; `detail.code="rate_limited"` | Solo traduce el 429 del proveedor | No |
| Cuota | Preguntas/día por usuario (`daily_usage`), `GET /auth/usage`; no bloquea en backend | Euros/día y mes por empresa, 429 `ai_quota_*_exhausted` con `resets_at`, `GET /api/agent/quota` | `SPEND_CAP_USD` (dudoso que se use) | Límite diario en n8n |
| Adjuntos | 1 imagen base64 en el JSON | Hasta 3 imágenes base64 en el JSON, se quitan al persistir | Audio multipart a `/transcriptions` | No |
| Errores | `HTTPException` estándar; en el stream, `str(e)` crudo | `detail` a veces con `{code,...}`; `error_id` solo en el stream | `{error:{code, message, request_id, details}}` con handlers globales | `detail=str(e)` |
| Request id | No | `RequestContextMiddleware`, respeta `X-Request-ID` | `request_context`, siempre genera uno | No |
| App | `app` global, `lifespan` con init de IA en background y 503 hasta `graph_ready` | `app` global, `lifespan` con BD y consumidores; `get_db` SQLAlchemy | `create_app(settings)` con servicios en `app.state` y deps `Annotated` | `lifespan` con warmup |

### Frontend

| Pieza | aurora (Next) | ATI (Angular) | Vera (Vite+React) | rag_upv (widget n8n) |
|---|---|---|---|---|
| Streaming | fetch POST + reader | fetch POST + reader | Polling cada 2 s | El del widget |
| Lista de conversaciones | Sidebar desde backend | No; hilo en localStorage con TTL 1 h por `perfil.empresa.ámbito` | Lista desde backend | No |
| Nueva conversación | UUID nuevo en cliente | `clearThread` | `POST /sessions` | Borra `sessionId` |
| Feedback | No | Pulgares con `message_id` del `done` | No | No |
| Cuota en la UI | Consulta `/auth/usage`, popup, bloquea composer, sondeo 60 s, fail-open | Consulta `/agent/quota` + 429 con código, aviso, bloquea composer hasta `resets_at`, fail-open | Mensaje de texto | Mensaje normal |
| Fuentes | Recursos en `done.metadata` | Evento `enrichment` con tarjetas y modal | No | Enlaces Markdown |
| Si falla | Texto vuelve al composer | Texto y ficheros vuelven al composer | Botón reintentar | — |
| Copiar respuesta | Sí (2 s "Copiado") | Sí | No | Sí |
| Auth | Backend propio, tokens en localStorage, refresh en 401 | supabase-js, guards | GoTrue REST directo, refresh previo a 60 s y en 401 | No |

## Qué cubren ya las recetas

- `langgraph-graph`: grafo, `stream_answer` e `invoke` con los eventos `token`, `tool_start`, `tool_end`, `routing`, `error` y `done`. El endpoint de FastAPI solo está como ejemplo en el `RECIPE.md`.
- `agent-memory`: `MemoryKey`, ventana por turnos, idempotencia por id de mensaje, backends RAM y SQL. `add_messages` devuelve el id de la respuesta (base para el feedback).
- `react-agent-chat`: parser SSE, estado del chat, cancelar, errores con `error_id`, Markdown seguro, `conversation_id` generado en cliente, borrador restaurado al fallar.

## Qué falta y es reutilizable

Patrones que aparecen en dos o más proyectos y no tienen receta:

1. **`fastapi-base`**: `create_app(settings)` (Vera), `lifespan`, servicios en `app.state`, dependencias `Annotated`, `CORSMiddleware`, request id (ATI y Vera), formato de error único `{error:{code, message, request_id}}` con handlers globales (Vera, y parcialmente ATI), `/docs` solo en desarrollo (ATI, Vera, UPV).
2. **`auth-verifier`**: `HTTPBearer` + `TokenVerifier` con factory (Supabase, JWT local, doble de test); `CurrentUser` con tenant y rol. Aurora y ATI sacan tenant y usuario del JWT; Vera añade roles con `require_roles`.
3. **`agent-chat-api`**: router con `POST /agent/chat` (JSON) y `POST /agent/stream` (SSE), `conversation_id` opcional con `uuid4` del servidor, `MemoryKey` desde el token, guards en orden (acceso → cuota → rate limit → saneado), `done{conversation_id, message_id}`, error en el stream con `error_id`. Aurora y ATI son casi idénticos.
4. **`conversation-history`**: `GET /conversations` y `GET /conversations/{id}/messages` sobre la tabla de `agent-memory` (aurora y Vera). Título = primer mensaje recortado (aurora). Borrar y renombrar no existen en ningún proyecto: se añadirían como extensión.
5. **`agent-feedback`**: pulgares sobre `message_id` del `done` (solo ATI, pero cierra el ciclo con `agent-memory`): tabla `agent_feedback`, UPSERT, comprobación de propiedad.
6. **`rate-limit-quota`**: ventana deslizante por usuario con 429 `rate_limited` (aurora y ATI) y cuota con `GET /agent/quota {available, exhausted, resets_at}` (aurora y ATI). Backend en settings: memoria o Redis.
7. **Frontend, extensiones de `react-agent-chat`**: lista de conversaciones (aurora y Vera), aviso de cuota que bloquea el composer con fail-open (aurora y ATI), pulgares (ATI), copiar respuesta (tres proyectos), sugerencias fijas en el estado vacío (aurora y ATI), imágenes en base64 con vista previa (aurora y ATI).

### Dudas

- Aurora no bloquea por cuota diaria en el backend; solo el front. No está claro si es intencionado.
- `SPEND_CAP_USD` en Vera parece heredado del prototipo; no se ha comprobado si la API lo aplica.
- Ningún proyecto borra ni renombra conversaciones: cualquier receta que lo incluya sería diseño nuevo, no un patrón extraído.
