# langgraph-graph

## Cuándo usarla

Cuando el flujo tenga **pasos fijos** alrededor de uno o varios agentes: clasificar o enrutar, rechazar, llamar al agente, postprocesar. Es el caso habitual de un chat con router y un agente con tools, expuesto como JSON y como SSE.

**Requiere la receta `langchain-agent`**, copiada en el mismo `agentic/`.

## Qué incluye

```
agentic/
  graph/
    state.py            GraphState (Pydantic): contrato de datos entre nodos
    nodes.py            RouterNode, AgentNode, RejectNode: @staticmethod async invoke(state, runtime)
    edges.py            route_after_router(state) -> nombre del nodo
    builder.py          build_graph() con la topología y compile_graph(), compilado una vez sin checkpointer
    graph.py            ainvoke_graph() (JSON) · astream_graph() (SSE) · run_config() (observabilidad)
    event_processor.py  astream_events v2 → SSEEvent; guarda el estado final
    events.py           SSEEvent y EventType (token, tool_start, tool_end, routing, error, done)
  memory/
    base.py             ABC Memory: ventana por TURNOS que nunca separa una tool de su resultado
    models.py           MemoryKey(tenant_id, user_id, conversation_id)
    in_memory.py        para tests y desarrollo
    sql.py              SqlMemory (SQLAlchemy 2: Postgres o Supabase; SQLite en tests)
    factory.py          MemoryFactory.create(MemoryBackend.X)
  registry.py           frontera de cableado: construye y cachea los agentes
  conversation.py       answer_question() y stream_answer(): memoria → grafo → persistencia
tests/
  test_graph.py         8 tests: enrutado, fail-open, memoria, streaming, errores, SQL
```

Topología de ejemplo:

```
START → router_node ─┬→ agent_node ──→ END
                     └→ reject_node ─→ END
```

## Decisiones

- **El grafo coordina y el agente vive dentro de un nodo.** `AgentNode` llama a `agent.process(...)`. Nunca se añade el agente como subgrafo, no hay supervisor y el bucle de tools ocurre dentro del agente.
- **State en Pydantic** con `Field(description=...)`. Los nodos devuelven un dict solo con las claves que escriben. Solo hace falta un reducer (`Annotated[list, operator.add]`) en claves que escriben varias ramas paralelas.
- **Nodos como clases** con `@staticmethod async invoke(state, runtime)`. Sus nombres son constantes y la topología solo existe en `build_graph()`.
- **Dependencias desde `registry`.** Los nodos no construyen agentes. La app llama a `registry.configure(...)` en el `lifespan` y los tests a `registry.override(...)`. Los agentes se cachean por idioma, con `asyncio.Lock` y doble comprobación.
- **Contexto tipado.** `context_schema=AgentContext`, pasado como `context=` y leído con `runtime.context`. El tenant no va en el state.
- **Sin checkpointer, con memoria propia.** La ventana se cuenta en turnos. `MemoryKey` siempre filtra por los tres ids y se persiste antes de responder.
- **Un grafo, dos modos.** `ainvoke` para JSON y `astream_events(v2)` con `EventProcessor` para SSE. Los tokens solo salen del nodo del agente, así que la salida estructurada del router no llega al usuario. Los eventos propios se emiten con `adispatch_custom_event`.
- **Errores.** El router falla abierto (si cae, la pregunta pasa al agente). En streaming, un error se convierte en el evento `error` con un `error_id` y sin el detalle, que solo va a los logs.
- **Observabilidad** por callbacks en `run_config()` (Langfuse, Opik o LangSmith), nunca dentro de los nodos.

## Cómo adaptarla

1. Copia primero la receta `langchain-agent` y luego `files/` de esta en el mismo sitio.
2. **Tu topología:** añade campos a `GraphState`, nodos a `nodes.py` (con su constante), condiciones a `edges.py` y conéctalo todo en `build_graph()`.
3. Cambia `ALLOWED_CATEGORIES` y `REJECT_TEXT` en `nodes.py`, o elimina el router si no lo necesitas.
4. **Memoria en producción:** crea la tabla `agent_messages`, ya sea con `metadata.create_all(engine)` o con una migración Alembic usando la `Table` de `sql.py`, y usa `MemoryFactory.create(MemoryBackend.SQL, session_factory=SessionLocal)`.
5. **FastAPI:**

   ```python
   @asynccontextmanager
   async def lifespan(app):
       registry.configure(settings=LLMSettings(openai_api_key=...), document_search=my_service)
       compile_graph()
       app.state.memory = MemoryFactory.create(MemoryBackend.SQL, session_factory=SessionLocal)
       yield

   @router.post("/agent/chat")
   async def chat(body: ChatIn, user=Depends(current_user)):
       key = MemoryKey(user.tenant_id, user.id, body.conversation_id)
       ctx = AgentContext(tenant_id=user.tenant_id, user_id=user.id, language=body.language)
       return {"answer": await answer_question(body.question, key=key, context=ctx, memory=app.state.memory)}

   @router.post("/agent/stream")
   async def stream(body: ChatIn, user=Depends(current_user)):
       ...
       events = stream_answer(body.question, key=key, context=ctx, memory=app.state.memory)
       return EventSourceResponse(e.to_sse() async for e in events)   # sse-starlette
   ```

   `tenant_id` y `user_id` salen siempre del token, nunca del body.

**Dependencias** (además de las de `langchain-agent`): `sqlalchemy>=2.0`, un driver Postgres (`psycopg[binary]`) y `sse-starlette` para el streaming.

Para comprobarla: `pytest` con las dos recetas copiadas.

## Origen

- Router → agente | rechazo, State Pydantic, `context_schema`, nodos `@staticmethod invoke`, `build_graph()` compartido entre invoke y stream, `EventProcessor`, memoria por turnos sin checkpointer y `registry` con caché: ATI_PLATFORM.
- Nodos como clases, una topología común para invoke y stream y errores saneados con `request_id`: aurora.
- Fan-out y join para ramas paralelas, y reducers solo donde hay concurrencia: Vera-Symplia y rag_tool_upv.
