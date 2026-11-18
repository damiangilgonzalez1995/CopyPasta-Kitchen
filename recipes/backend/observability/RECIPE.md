# observability

## Cuándo usarla

Para **ver qué hace cada turno del agente**: la traza completa (nodos, llamadas al LLM, tools) en Langfuse, Opik o LangSmith elegido en `.env`, y, con o sin proveedor, los tokens, el coste y la duración de cada turno en una línea de log y en un `TurnSummary` que puedes guardar. Sin configuración no traza nada y la app arranca igual.

No depende de otras recetas. **Usa `project-settings`** (bloque `ObservabilitySettings`) y **encaja con `agent-chat-api`** (`create_app(tracer=...)`), que ya llama a `begin_turn` y `finish` en cada turno.

## Qué incluye

```
observability/
  models.py            TracingProvider · RunInfo (thread, tenant, user, request_id, tags) · TokenUsage · ModelPrice · Prices · TurnSummary
  usage.py             UsageCollector (callback: tokens de cada llamada al chat model) · usage_from_messages (lo mismo sobre mensajes guardados)
  tracer.py            Tracer (ABC: _callbacks, _metadata, _trace_id, _flush) · NullTracer · TurnTrace (config del run + finish() → TurnSummary)
  langfuse_tracer.py   LangfuseTracer: un cliente por proceso, un CallbackHandler por run, session = thread_id, user = user_id
  opik_tracer.py       OpikTracer: OpikTracer del SDK por run con thread_id (vista Threads), tags y metadata
  langsmith_tracer.py  LangSmithTracer: LangChainTracer explícito con Client propio (nada por variables de entorno)
  settings.py          bloque ObservabilitySettings: TRACING_PROVIDER (none por defecto), TRACING_TAGS, LANGFUSE_*, OPIK_*, LANGSMITH_*
  factory.py           TracingFactory.create(settings, prices=): nunca lanza; proveedor que falla → NullTracer con warning
tests/test_observability.py  12 tests sin red: tokens y caché, coste con descuento y None sin precio, collector en un chat model,
                             metadata/tags al handler, fail-open (begin, flush, timeout), settings, factory con los tres SDK offline
pytest.ini
```

## Decisiones

- **El core no sabe quién observa.** `agentic/` solo recibe un `config` (`callbacks`, `metadata`, `tags`, `run_name`); quien lo construye es `Tracer.begin(...)` en la capa de la API. Los nodos nunca importan el SDK.
- **Un `Tracer` por proceso, un `TurnTrace` por turno.** `begin` construye el handler del proveedor para ese run con el `thread_id` del servidor (tenant como namespace, como `MemoryKey.thread_id`), el tenant, el usuario y el `X-Request-ID`: la traza y la línea de log se cruzan por el mismo id, algo que los proyectos de origen no llegaban a hacer.
- **Apagado por defecto y fail-open.** `TRACING_PROVIDER=none` no construye nada. Si el SDK falta o la configuración es mala, la factory deja `NullTracer` y un warning; si el handler falla al construirse, el turno corre sin traza; si el flush falla o tarda, se corta con timeout (`TRACING_FLUSH_TIMEOUT_SECONDS`). En el log solo va la clase del error: el texto puede llevar la clave.
- **Tokens y coste sin depender del proveedor.** `UsageCollector` lee `usage_metadata` de cada respuesta del chat model, con `input_token_details.cache_read`. El coste es `(entrada − caché)·p_in + caché·p_caché + salida·p_out` por millón. Los precios los pone el proyecto (`Prices`); un modelo sin precio da `cost_usd=None`, nunca 0: un coste desconocido no se reporta como gratis.
- **`TurnSummary` es el dato, la línea de log es la vista.** Lo que un proyecto guarda en su tabla de gasto diario o en filas de traza sale de aquí: `summary.model_dump()` a tu tabla de gasto, a `rate-limit-quota` (`QuotaUnit.TOKENS`) o a la página de admin.
- **LangSmith explícito, no por variables de entorno.** `LANGSMITH_TRACING=true` en el entorno traza cualquier LangChain del proceso, también en tests. Aquí es un `LangChainTracer` con `Client` propio, solo en los runs que pasan por `begin`.
- **Sin spans manuales ni filtrado del ruido de LangGraph.** Filtrar los nodos que no aportan o trazar a mano un clasificador o una búsqueda es una subclase de `Tracer` (`_callbacks` devolviendo tu handler) y no parte de esta receta.
- **Sin feedback ni prompts en el proveedor.** Los pulgares no se mandan como score, y los prompts viven en YAML (`langchain-agent`). Si quieres el score, `tracer.trace_id` del `TurnSummary` es lo que hay que guardar junto al `message_id`.

## Cómo adaptarla

1. Copia `files/` en la raíz del backend. Sustituye `{{app_name}}` en `observability/settings.py` (nombre de proyecto en Opik y LangSmith).
2. **Settings:** `class Settings(ObservabilitySettings, LLMSettings, BaseAppSettings)`. En el `.env`, uno de:

   ```
   TRACING_PROVIDER=langfuse   LANGFUSE_PUBLIC_KEY=pk-lf-...  LANGFUSE_SECRET_KEY=sk-lf-...  LANGFUSE_HOST=https://cloud.langfuse.com
   TRACING_PROVIDER=opik       OPIK_URL_OVERRIDE=http://localhost:5173/api   (o OPIK_API_KEY + OPIK_WORKSPACE para Cloud)
   TRACING_PROVIDER=langsmith  LANGSMITH_API_KEY=lsv2_...  LANGSMITH_PROJECT={{app_name}}
   TRACING_TAGS=prod,eu
   ```

   e instala solo el SDK que uses (`langfuse`, `opik` o `langsmith`).
3. **Precios** (opcional): `Prices(by_model={"gpt-4.1-mini": ModelPrice(input=0.4, output=1.6, cached_input=0.1)})` en tu `main.py` o desde un YAML del proyecto.
4. **`main.py`** con `agent-chat-api`:

   ```python
   tracer = TracingFactory.create(settings, prices=prices)
   app = create_app(settings=settings, ..., tracer=tracer)   # cada turno: begin_turn -> config -> finish; flush al apagar
   ```

   Sin `agent-chat-api`: `trace = tracer.begin(RunInfo(thread_id=..., tenant_id=..., user_id=..., request_id=current_request_id()))`, pasa `trace.config` a `answer_question(..., config=...)` o a `graph.ainvoke(..., config=...)`, y en un `finally` `summary = trace.finish(error)`. Al apagar, `await tracer.flush()`.
5. **Guardar el gasto:** en `traced_turn` (o donde llames a `finish`) toma el `TurnSummary` y escríbelo donde toque; `usage_from_messages(new_messages)` da lo mismo a partir de la memoria si prefieres calcularlo al persistir.
6. **Proveedor nuevo o spans propios:** subclase de `Tracer` con `_callbacks(run)`, `_metadata(run)`, `_trace_id(run)` y `_flush()`, y un caso en `TracingFactory`.
7. Para comprobarla: `pytest` (12 tests; los de cada SDK se saltan si no está instalado). Con `agent-chat-api` y sus requeridas: 98 tests.

**Dependencias:** `langchain-core`, `pydantic-settings`; `langfuse>=3` (probado con 5.2), `opik` (2.2) o `langsmith` (0.15) según el proveedor.

## Origen

- Probado en producción: tracer construido una vez con import perezoso del SDK, apagado si falta la configuración y `[]` con warning si falla; `thread_id` del servidor en `metadata`; `Tracer.begin(...) -> TurnTrace` con `callbacks`, `metadata`, `finish` y `flush` con timeout en hilo; `NullTracer`; cada llamada al SDK en `try/except` y solo la clase del error al log; coste `None` si el modelo no tiene precio; cliente `Langfuse` por proceso y handler por turno; tokens desde `usage_metadata` con `cache_read` y coste por millón; registro de gasto que nunca propaga errores.
- Nuevo en esta receta: `request_id` en la traza (en producción estaba en el log pero no se cruzaba con la traza) y `LangChainTracer` explícito en lugar de LangSmith por variables de entorno, que trazaba también en tests.
