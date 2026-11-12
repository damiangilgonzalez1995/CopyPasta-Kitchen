# conversation-history

## Cuándo usarla

Para que el chat tenga **barra lateral e historial**: listar las conversaciones del usuario (título, fechas, número de mensajes, paginado), cargar los mensajes de una y borrarla. Lee la misma memoria que escribe el chat: no hay segundo almacén ni sincronización.

**Requiere `agent-chat-api`** (y con ella `agent-memory`, que aporta `get_history` y `list_conversations`): usa su `get_current_user`, su `get_memory` y su `create_app`.

## Qué incluye

```
api/conversations/
  router.py     GET /conversations?limit&offset · GET /conversations/{id}/messages · DELETE /conversations/{id}
  schemas.py    ConversationOut · ConversationsResponse · MessageOut (user | assistant) · ConversationMessagesResponse
tests/test_conversations_api.py   5 tests: 401, orden y títulos y paginación, solo texto visible, 404 ajeno/desconocido, borrar
pytest.ini
```

## Decisiones

- **La memoria es la fuente.** `Memory.list_conversations` y `Memory.get_history` (receta `agent-memory`) hacen el trabajo; el router solo adapta. Aurora y Vera lo hacen así; una tabla aparte de conversaciones obligaría a mantenerla en cada turno.
- **Lo ajeno es un 404, no un 403.** Todas las rutas construyen la `MemoryKey` con tenant y usuario del token, así que el id de otro no existe en tu espacio. No se revela si existe.
- **Solo texto visible.** `MessageOut` mapea `human → user` y `ai → assistant` y descarta tool calls, resultados de tools y mensajes vacíos. En la base de datos sigue todo (el LLM lo necesita). Cada mensaje lleva su `id` almacenado: es el `message_id` que `agent-feedback` vota.
- **Título = primer mensaje humano recortado** (aurora). Se calcula en la memoria (`title_from`), no en el router, para que SQL lo haga en una consulta.
- **Orden por última actividad**, con `limit` (máx. 200) y `offset` como aurora. Sin total: ningún proyecto de origen lo devuelve y la barra lateral no lo necesita.
- **Borrar es `Memory.clear`.** No existe en los proyectos de origen; se añade porque el contrato de memoria ya lo tenía ("el usuario pide olvidar"). 204, y 404 si no era tuya. Renombrar queda fuera: requeriría guardar el título.
- **Mismo patrón de montaje** que `rate-limit-quota`: `app.include_router(conversations_router)` tras `create_app`. Sin el kill switch del agente: el historial se puede leer aunque el chat esté apagado.

## Cómo adaptarla

1. Copia `files/` en la raíz del backend, encima de `agent-chat-api`.
2. **`main.py`:**

   ```python
   from api.conversations.router import router as conversations_router
   app = create_app(...)
   app.include_router(conversations_router)
   ```

3. **Frontend:** `GET /conversations` al cargar la barra lateral; al pulsar una, `GET /conversations/{id}/messages` y seguir el hilo mandando ese `conversation_id` a `POST /agent/chat` o `/stream`. Tras un `done`, refrescar la lista (el título aparece con el primer turno).
4. **Fechas:** ISO 8601 en UTC (`2026-03-30T10:00:00Z`). Si el negocio quiere otra zona, se convierte en el cliente.
5. Para comprobarla: `pytest` con las recetas backend copiadas (114 tests con las siete).

**Dependencias:** las de `agent-chat-api`.

## Origen

- `GET /conversations` paginado con `ConversationSummary{session_id, title, created_at, updated_at}` y `GET /conversations/{id}/messages` con 404 si no existe o es de otro usuario, leyendo de la memoria: aurora (`api/routers/conversations.py`).
- Listado paginado con `limit` y `offset` y una vista por conversación: Vera-Symplia (`routers/admin_conversations.py`, versión de administración).
- `DELETE`, `message_count`, filtrado de tools en la respuesta y los ids de mensaje en el historial: nuevos.
