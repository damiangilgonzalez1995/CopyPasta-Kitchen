# agent-memory

## Cuándo usarla

Cuando un agente, suelto o dentro de un grafo, tenga que **recordar la conversación** entre peticiones: chat multiusuario y multitenant, con el historial persistido y una ventana acotada que se reenvía al LLM.

No sirve para memoria a largo plazo (hechos del usuario, resúmenes o búsqueda semántica en recuerdos). No aparece en ningún proyecto de origen.

No depende de otras recetas. **Usa `project-settings`**: trae el bloque `MemorySettings` para heredarlo en el `Settings` del proyecto.

## Qué incluye

```
agentic/memory/
  models.py      MemoryKey (tenant, user, conversation; inmutable) · MemoryBackend (in_memory | sql) · HistoryMessage · ConversationSummary · title_from
  settings.py    bloque MemorySettings: MEMORY_BACKEND (obligatorio) y MEMORY_WINDOW_TURNS (10)
  base.py        ABC Memory: ventana por turnos, escritura idempotente, get_history, list_conversations, clear(), id de la respuesta
  in_memory.py   InMemoryMemory: tests y desarrollo local
  sql.py         SqlMemory + tabla agent_messages (SQLAlchemy 2: Postgres o Supabase; SQLite en tests)
  factory.py     MemoryFactory.create(settings, session_factory=...)
tests/
  memory_conformance.py   lo que TODO backend debe cumplir (14 tests) + FakeClock
  test_memory.py          conformidad en los dos backends + settings y factory (34 tests)
pytest.ini
```

## Decisiones

- **El backend se elige en los settings, no en el código.** `MEMORY_BACKEND=in_memory` o `sql`, y `MemoryFactory` construye la implementación. Pasar de RAM a Postgres es cambiar una variable. **No hay valor por defecto**: caer en memoria del proceso "por si acaso" convertiría un error de configuración en historial perdido en cada reinicio.
- **Clase base y conformidad.** `Memory` (ABC) fija el contrato y cada backend implementa `_fetch_recent_turns`, `_append` y `clear`. Todos pasan la misma `MemoryConformance`. Un backend nuevo (Redis, Mongo…) es una subclase, una rama en la factory y una clase de test.
- **Ventana en turnos, no en mensajes.** Un turno es un mensaje humano y todo lo que el agente hizo por él. Así la ventana siempre empieza en un mensaje humano y nunca separa una tool de su resultado, que los proveedores rechazan. Además, un agente que usa más tools no recuerda menos. En la base de datos se guarda todo y la ventana solo limita lo que se lee.
- **`MemoryKey` con los tres ids, siempre.** El `conversation_id` lo elige el cliente; `tenant_id` y `user_id` salen del token. La clave es inmutable y `SqlMemory._thread` es el único sitio que filtra.
- **Escritura idempotente por `message.id`.** Un reintento no duplica mensajes. Los mensajes sin id se añaden siempre, así que conviene darle al mensaje humano el id del cliente (`HumanMessage(text, id=client_message_id)`).
- **`add_messages` devuelve el id de la última respuesta** (un `AIMessage` con texto), útil para que el frontend vote o dé feedback.
- **Dos lectores.** `get_messages` devuelve la ventana para el LLM; `get_history` devuelve el hilo completo con `created_at` para la interfaz, y `list_conversations` el listado del usuario (más reciente primero, título = primer mensaje humano recortado, paginado). Es lo que expone la receta `conversation-history`. El reloj (`clock`) se inyecta para que los tests fijen las fechas.
- **Sin checkpointer de LangGraph.** La memoria es independiente del grafo: quien llama lee la ventana, ejecuta el agente y guarda los mensajes nuevos.
- **Asíncrona incluso en RAM.** El contrato lo marca el backend más lento. En SQL, las consultas síncronas van en `asyncio.to_thread`.

## Cómo adaptarla

1. Copia `files/` en la raíz del backend, junto al `agentic/` de las otras recetas.
2. **Settings:** en el `Settings` del proyecto (receta `project-settings`):

   ```python
   from agentic.memory.settings import MemorySettings

   class Settings(MemorySettings, BaseAppSettings): ...
   ```

   En el `.env`: `MEMORY_BACKEND=sql` y, si quieres, `MEMORY_WINDOW_TURNS=10`.
3. **Tabla:** `metadata.create_all(engine)` o una migración Alembic con la `Table` de `sql.py`.
4. **Construirla una vez** en el arranque (FastAPI `lifespan`) con la sesión de la app:

   ```python
   memory = MemoryFactory.create(get_settings(), session_factory=SessionLocal)
   ```

5. **Un turno con un agente suelto:**

   ```python
   key = MemoryKey(tenant_id=user.tenant_id, user_id=user.id, conversation_id=body.conversation_id)
   history = await memory.get_messages(key)
   turn = await agent.process(body.question, context=ctx, history=history)
   answer_id = await memory.add_messages(key, turn.new_messages)
   ```

6. **Nuevo backend:** una subclase de `Memory`, un valor en `MemoryBackend`, una rama en `MemoryFactory` y `class TestXMemory(MemoryConformance)` con su fixture `memory`.

**Dependencias:** `langchain-core`, `pydantic-settings>=2.6`, `sqlalchemy>=2.0` y un driver Postgres (`psycopg[binary]`) para SQL; `pytest` y `pytest-asyncio` para los tests.

## Origen

- ABC `Memory`, `MemoryKey` con los tres ids e inmutable, ventana por turnos con red de seguridad en el mensaje humano, `MemoryFactory` sin valor por defecto, Postgres con `session_factory` inyectada y el id de la última respuesta: ATI_PLATFORM (`agentic/memory/`).
- Backend elegido en los settings y factory que lo valida (`AgentMemoryFactory`), escritura idempotente (por `client_id`) y tests de conformidad comunes a todos los backends: Vera-Symplia.
- Memoria a través de un servicio externo (MCP sobre Qdrant), sin clase base: aurora. No se ha incluido.
- `clear()` es nuevo: no estaba en los proyectos de origen.
