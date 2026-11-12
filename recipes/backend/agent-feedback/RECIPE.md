# agent-feedback

## Cuándo usarla

Para los **pulgares arriba y abajo** sobre las respuestas del agente: un voto por usuario y respuesta (volver a votar lo actualiza), con comentario opcional, deshacer y recuperar los votos de una conversación para pintar el estado al recargar. Cierra el ciclo con el `message_id` que ya devuelven `done`, `ChatResponse` y el historial.

**Requiere `agent-chat-api`** (usa su `get_current_user`, `get_memory`, `require_agent_enabled` y `create_app`). **Usa `project-settings`** (bloque `FeedbackSettings`). El núcleo `feedback/` no importa FastAPI ni el agente.

## Qué incluye

```
feedback/
  models.py       FeedbackBackend · Rating (+1 | -1) · FeedbackVote · Feedback (con fechas) · FeedbackResult
  base.py         FeedbackStore (ABC): vote (upsert) · get · list_for_conversation · remove; subclase: _save, get, list, remove
  in_memory.py    InMemoryFeedbackStore (tests y desarrollo)
  sql.py          SqlFeedbackStore + tabla agent_feedback (SQLAlchemy 2; UNIQUE tenant+user+message, CHECK rating)
  settings.py     bloque FeedbackSettings: FEEDBACK_BACKEND (obligatorio)
  factory.py      FeedbackFactory.create(settings, session_factory=...)
api/feedback/
  router.py       POST /agent/feedback · GET /agent/feedback?conversation_id= · DELETE /agent/feedback/{message_id}
  schemas.py      FeedbackRequest{conversation_id, message_id, rating, comment?} · FeedbackResponse (+ created_or_updated)
tests/
  feedback_conformance.py   lo que TODO backend debe cumplir (6 tests) y FakeClock
  test_feedback.py          conformidad en RAM y SQL, modelos, settings y factory (16 tests)
  test_feedback_api.py      guards, crear → actualizar, 404 único, deshacer (4 tests)
pytest.ini
```

## Decisiones

- **Un voto por (tenant, usuario, mensaje), upsert.** Como ATI: votar otra vez cambia `rating` y `comment` y conserva `created_at`. La respuesta dice `created` o `updated`.
- **La propiedad se comprueba en la memoria, no en la tabla de votos.** El mensaje debe ser una respuesta del agente (`ai` con texto) dentro de una conversación del propio usuario; se lee con `Memory.get_history`. Por eso el voto lleva `conversation_id` además de `message_id` (ATI solo necesita el segundo porque consulta su tabla de mensajes por id; aquí la memoria es un contrato, no una tabla).
- **Un solo 404.** Mensaje inexistente, de otro usuario o tenant, humano, o una tool call: la misma respuesta, para no filtrar qué existe (ATI).
- **Mismos guards que el chat:** agente apagado → 404, sin token → 401. No pasa por el rate limit del turno: votar no gasta LLM.
- **Backend en settings** (`FEEDBACK_BACKEND=in_memory | sql`), sin valor por defecto, como las demás recetas. La tabla no lleva clave foránea a los mensajes porque la receta no conoce tus nombres de tabla; añádela en tu migración si quieres borrado en cascada.
- **`GET /agent/feedback?conversation_id=`** devuelve los votos del usuario en esa conversación para restaurar los pulgares al recargar. ATI no lo tiene (el estado vive solo en el cliente); se añade porque sin él el historial de `conversation-history` llega sin votos.
- **`rating` como `Literal[-1, 1]`:** Pydantic rechaza cualquier otro valor con 422, no hace falta el 400 manual de ATI.
- **Reloj inyectable** y async en todos los backends, igual que `agent-memory` y `rate-limit-quota`.

## Cómo adaptarla

1. Copia `files/` en la raíz del backend, encima de `agent-chat-api`.
2. **Settings:** `class Settings(FeedbackSettings, BaseAppSettings)`. En el `.env`: `FEEDBACK_BACKEND=sql`.
3. **Tabla:** `metadata.create_all(engine)` o una migración con la `Table` de `feedback/sql.py`.
4. **`main.py`:**

   ```python
   from api.feedback.router import router as feedback_router
   app = create_app(...)
   app.state.feedback_store = FeedbackFactory.create(settings, session_factory=SessionLocal)
   app.include_router(feedback_router)
   ```

5. **Frontend:** tras `done{conversation_id, message_id}` muestra los pulgares; al pulsar, `POST /agent/feedback`; para quitar el voto, `DELETE /agent/feedback/{message_id}`; al abrir una conversación del historial, `GET /agent/feedback?conversation_id=` y cruza por `message_id` con los mensajes de `conversation-history`.
6. **Otro backend:** subclase de `FeedbackStore` con `_save`, `get`, `list_for_conversation` y `remove`, una rama en `FeedbackFactory` y una clase de test que herede de `FeedbackConformance`.
7. Para comprobarla: `pytest` con las recetas backend copiadas (134 tests con las ocho).

**Dependencias:** `pydantic`, `pydantic-settings`; `sqlalchemy` para SQL; las de `agent-chat-api` para `api/`.

## Origen

- `POST /api/agent/feedback {message_id, rating ±1}` con UPSERT por (mensaje, usuario), `created_or_updated` en la respuesta, comprobación de propiedad (tenant, usuario y `role = 'ai'`) con un único 404, flag del agente → 404 antes que nada, tabla `agent_feedback` con `UNIQUE(agent_message_id, user_id)` y `CHECK(rating IN (-1, 1))`, columna `comment` reservada: ATI_PLATFORM (`api/routes/agent_feedback.py`, `models/agent_feedback.py`).
- Store como clase base con backends por settings, `conversation_id` en el voto para comprobar la propiedad contra la memoria, `GET` por conversación y `DELETE` para deshacer: nuevos.
