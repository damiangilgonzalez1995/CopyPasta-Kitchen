# Patrón agéntico: grafo LangGraph + agente LangChain

Síntesis cruzada de los 4 proyectos de origen. El detalle por proyecto está en `analysis/<proyecto>.md`.

| Proyecto | Grafo (A) | Agente (B) | Fecha del código analizado |
|---|---|---|---|
| aurora (rama `docs/cloud-deployment`) | ✅ router → tool_agent → next_steps \| no_tools | ✅ `BaseAgent` + `create_agent`, tools desde MCP | 2026-09-27 |
| ATI_PLATFORM | ✅ router → agent \| reject | ✅ `BaseAgent` + `create_agent` + middleware | 2026-11-05 |
| Vera-Symplia | ✅ classify → (search ∥ capture) → merge → decide → [agent] → output | ✅ `BaseAgent` + `create_agent` + `response_format` + middleware | 2026-11-10 |
| rag_tool_upv | ✅ pipelines RAG deterministas (`Send`, `Command`) | ❌ (el agente está en n8n; Python solo usa cadenas LCEL) | 2026-10-16 |

**Evolución visible:** aurora → ATI → Vera. Vera cita literalmente "una clase por nodo, como en Aurora". rag_tool_upv es un caso distinto (grafo como pipeline, sin agente) y es la referencia para la receta de **grafo sin agente**.

---

## La idea central

> **El grafo orquesta un flujo fijo; el agente (`create_agent`) vive DENTRO de un nodo.**

- El grafo es determinista: router/clasificador → rama → salida. Sin supervisor ni multi-agente.
- El bucle ReAct (LLM ↔ tools) ocurre dentro del agente, no en aristas del grafo.
- El agente nunca se añade como subgrafo (`add_node(compiled)`): el nodo lo llama con `ainvoke`/`astream`.
- Siempre `langchain.agents.create_agent` (LangChain v1). **Nunca `create_react_agent`.**

---

## (A) Grafo LangGraph

| Aspecto | Patrón común | Variantes |
|---|---|---|
| **State** | Un único modelo de estado, contrato entre nodos | Pydantic (aurora, ATI) · TypedDict `total=False` (Vera, rag) |
| **Reducers** | Solo donde varios nodos escriben a la vez | `Annotated[list, operator.add]` (ATI, rag) · `operator.or_` para `timings` (Vera) · ninguno (aurora) |
| **Contexto** | Pydantic aparte (`Context`/`AgentContext`) como `context_schema`; lleva tenant/user/idioma; **el LLM nunca lo ve** | rag usa `config["configurable"]` en su lugar |
| **Nodos** | **Una clase por nodo** | `@staticmethod async invoke(state, runtime)` (aurora, ATI) · `async __call__` con deps por constructor + `TimedNode` (Vera) · funciones `x_node` (rag, lo más reciente) |
| **Nombres de nodo** | `snake_case`, constantes de módulo | sufijo `_node` (aurora, ATI, rag) |
| **Aristas** | Condicionales con función que devuelve el nombre del nodo | módulo `edges.py` (aurora, rag) · clase `Edges` con métodos estáticos `after_the_x` (Vera) · fan-out con lista / `Send`, join con `add_edge([a,b], c)` |
| **Builder** | Una función/clase `build_graph()` es el **único** sitio con la topología | aurora/ATI comparten topología entre modo invoke y modo streaming |
| **Compile** | Una vez por proceso (global / `lru_cache` / `lifespan`) | Vera: un grafo por job |
| **Checkpointer** | **No** (ATI, Vera, rag) — memoria propia | aurora: factory `MemorySaver`/`AsyncPostgresSaver` |
| **Memoria** | ABC `Memory` + factory (Postgres/Supabase/in-memory); ventana de N turnos; el agente es stateless (recibe historial, devuelve mensajes nuevos) | aurora: vía tools MCP |
| **Streaming** | `astream_events(v2)` → `EventProcessor` → SSE | Vera: `astream(stream_mode=["updates","custom"])` + `get_stream_writer()` |
| **Errores** | try/except por nodo → mensaje saneado con `request_id`; piezas auxiliares fail-open, seguridad fail-closed | Vera: `RetrievalError(kind, node)` sin texto + respuestas degradadas |

---

## (B) Agente LangChain

### Clase base (presente en aurora, ATI y Vera)

```python
class BaseAgent(ABC):
    def __init__(self, agent_type: AgentType, model: LLMModel, ..., llm: BaseChatModel | None = None): ...
    @abstractmethod
    def get_prompt(self) -> str: ...
    @abstractmethod
    async def process(self, state, ...) -> ...: ...     # punto de entrada desde el nodo
    def get_tools(self) -> Sequence[BaseTool]: return []        # Vera
    def get_middleware(self) -> Sequence[AgentMiddleware]: return []  # Vera
    async def initialize(self) -> None:                 # construye self.agent una vez
        self.agent = create_agent(model=self.llm, tools=..., system_prompt=...,
                                  context_schema=..., middleware=..., response_format=...)
```

Ciclo de vida común: `__init__` → `await initialize()` → `process()`.

| Aspecto | Patrón común | Variantes |
|---|---|---|
| **Qué fija la subclase** | modelo, prompt, tools, `response_format`, `context_schema` | Vera los declara como atributos de clase |
| **LLM** | Enum `LLMModel(provider, model_id[, reasoning_effort])` + `LLMProvider.create_from_model` (factory) | OpenAI siempre; + Groq (aurora), + Anthropic (Vera). Proveedor desconocido → `ValueError` |
| **Costura de tests** | Inyectar el LLM: `llm=` (ATI) · `chat_factory=` (Vera) | tests con `FakeListChatModel` |
| **LLM perezoso** | — | Vera: property `llm` + `close()` explícito |
| **Structured output** | `response_format=Pydantic` y leer `result["structured_response"]` (aurora, Vera) | ATI: texto plano en el agente principal; aurora duplica el agente sin `response_format` para hacer streaming de tokens |
| **Modelos de respuesta** | Pydantic con `Field(description=...)` en `agents/models.py` | |
| **Instancias** | Agentes singleton/cacheados, init con `asyncio.Lock` | ATI: caché por `(tenant, idioma)` en un `registry.py` |

### Tools

| Aspecto | Patrón común | Variantes |
|---|---|---|
| **Contexto seguro** | `runtime: ToolRuntime[Context]` → tenant/deps desde `runtime.context`, **nunca** desde los argumentos del LLM (los 3) | |
| **Definición** | — (cada proyecto distinto) | aurora: generadas desde MCP → `StructuredTool` · ATI: factory `build_*_tools(service, config)` con `StructuredTool.from_function` / `@tool` · Vera: subclases de una base `VeraTool(BaseTool)`, una por archivo |
| **Registro** | Una lista central | `ToolSet.default()` (Vera) · allowlist `KNOWN_TOOL_NAMES` (ATI) · `meta.agent_use` + yaml (aurora) |
| **Descripción** | String explícito, no docstring | ES (aurora, ATI) · EN (Vera) |
| **Salida** | Mantener el contexto del LLM pequeño | `content_and_artifact` (ATI) · `Command(update=...)` al estado + bridges (aurora) · `get_stream_writer()` para eventos (Vera) |
| **Errores** | La tool no propaga la excepción: devuelve un mensaje seguro | |

### Prompts

| Aspecto | Patrón común | Variantes |
|---|---|---|
| **Formato** | Texto plano como system prompt; **sin Jinja ni `ChatPromptTemplate`** en los agentes | |
| **Dónde** | — (cada proyecto distinto) | aurora: constantes Python en el servidor MCP + sync con LangSmith Hub · ATI: YAML versionado por idioma + `load_prompt` cacheado · Vera: clases Python (`XPrompt.TEXT`) con renderizadores estáticos |
| **Entrada** | Etiquetas XML para delimitar datos (`<text>`, `<captured>`…) | Vera, rag |
| **Paso a `create_agent`** | `system_prompt=` (ATI) | aurora/Vera montan `[SystemMessage, *historial, HumanMessage]` a mano |

### Middleware (ATI, Vera)

- `@wrap_model_call` / `AgentMiddleware.awrap_model_call` + `request.override(...)`.
- Usos: cambiar de modelo por nivel (ATI), recordatorio de idioma (ATI), presupuesto de rondas/tiempo quitando tools (Vera), log de mensajes (Vera).
- Se crean con factories `build_*_middleware()` (ATI) o se registran en `MiddlewareSet.default()` (Vera).

### Observabilidad

Siempre por **callbacks en el `config`** del run, nunca dentro del core: Opik (ATI), Langfuse (Vera), LangSmith solo por env vars (aurora, rag).

---

## Exposición a la API

- FastAPI. El grafo/agentes se construyen en `lifespan` o en un `registry` y se guardan en `app.state` o en caché de módulo.
- Dos modos sobre el mismo grafo: `POST /…/chat` (`ainvoke`) y `POST /…/stream` (SSE con `sse-starlette`).
- Vera: la API encola el job (202) y un worker ejecuta el grafo.
- Capa de IA aislada: ATI (`core/` no importa la app, ADR-024) y Vera (paquete `vera_ai` puro, ADR-010).

---

## Estructura de carpetas convergente

```
agentic/                      # o core/ o <pkg>_ai/
  agents/   base_agent.py · agents.py · models.py (response_format, AgentType) · state.py (contexto)
            middleware/
  graph/    state.py · builder.py · nodes.py · edges.py · graph.py (invoke) · streaming.py · event_processor.py
  tools/    base + una tool por archivo (o factory) + registro
  prompts/  loader + prompts
  llm/      models.py (enum LLMModel) · provider.py (factory)
  memory/   base.py (ABC) · factory.py · implementaciones
registry.py / ai/            # frontera de cableado con settings y la app
```

---

## Decisiones para la receta (2026-11-10)

| # | Tema | Decisión | Referencia |
|---|---|---|---|
| 1 | State del grafo | **Pydantic `BaseModel`** con `Field(description=...)`; reducers solo donde haya escritura concurrente | aurora, ATI |
| 2 | Nodos | **Clase con `@staticmethod async invoke(state, runtime)`**; nombres como constantes | aurora, ATI |
| 3 | Structured output | **Opcional**: `response_format` en la clase; si es `None` el agente devuelve texto | ATI + Vera |
| 4 | Prompts | **YAML versionado por idioma** (`prompts/<nombre>.<lang>.yaml`: `name`, `version`, `language`, `description`, `system`) + `load_prompt` cacheado con fallback de idioma | ATI |
| 5 | Tools | **Base propia sobre `BaseTool`**, una tool por archivo, contexto por `ToolRuntime`, fallo seguro, registro en `ToolSet.default()` | Vera |
| 6 | Memoria | **Memoria propia**: ABC `Memory` + factory (in-memory / Postgres), ventana de N turnos, grafo sin checkpointer | ATI, Vera |
| 7 | Proveedores LLM | **OpenAI, Anthropic, Azure OpenAI y Groq** en la factory `LLMProvider` + enum `LLMModel` | aurora, Vera (+ Azure nuevo) |

## Defectos observados (sin verificar en ejecución)

- aurora: `ToolNode` accede a `response["structured_response"]` cuando `process` devolvió un dict de error sin esa clave → KeyError enmascarado (`agents.py:186-192`, `nodes.py:53`).
- aurora: `RTCAgent` pasa el `Context` en `config["metadata"]` en vez de `context=` → el flujo de voz probablemente falla por `tenant_id`.
- aurora: `PlannerAgent`, `planner_result` y `consolidated_clips` definidos pero sin usar.
- rag_tool_upv: `chains.py:21-25` quitó `PydanticToolsParser` pero `_format_output` sigue iterando la salida de `bind_tools` como lista de modelos.
