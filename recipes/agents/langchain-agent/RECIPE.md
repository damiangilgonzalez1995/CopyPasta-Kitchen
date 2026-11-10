# langchain-agent

## Cuándo usarla

Cuando necesites **un agente LLM**, con o sin tools, construido con `langchain.agents.create_agent` (LangChain v1). Sirve sola o como pieza de un nodo de grafo (receta `langgraph-graph`).

No la uses para cadenas de una sola llamada sin agente (`prompt | model`). Tampoco para pipelines deterministas: para eso, un grafo sin agente.

## Qué incluye

```
agentic/
  __init__.py            regla: agentic/ no importa nada de la app
  context.py             AgentContext (tenant, user, idioma): lo leen tools y middleware, nunca el LLM
  llm/
    models.py            enum LLMModel(provider, model_id, reasoning_effort) + LLMProviderName
    settings.py          LLMSettings (claves inyectadas; from_env() para scripts)
    provider.py          LLMProvider.create_from_model → OpenAI | Azure OpenAI | Anthropic | Groq
  agents/
    base_agent.py        BaseAgent: plantilla sobre create_agent
    agents.py            AssistantAgent (tools, texto) y ClassifierAgent (sin tools, structured output)
    models.py            AgentType, AgentTurn, AgentError, modelos de response_format
  tools/
    base_tool.py         AppTool(BaseTool): fallo seguro, context_of(), emit()
    search_documents.py  tool de ejemplo con un servicio inyectado
    __init__.py          ToolSet.default(...): registro de tools
  prompts/
    loader.py            load_prompt(name, lang): YAML versionado, caché y fallback de idioma
    assistant.es.yaml    prompt de ejemplo (uno por idioma)
    assistant.en.yaml
  middleware/
    language.py          build_language_middleware(): @wrap_model_call + request.override
tests/
  fakes.py               ScriptedChatModel, tool_call(), FakeDocumentSearch
  test_agents.py         16 tests, sin API keys
pytest.ini
```

## Decisiones

- **`create_agent` y no `create_react_agent`**: es la API de LangChain v1 y admite `middleware`, `response_format` y `context_schema`.
- **Clase base con plantilla.** Una subclase solo declara lo que la distingue: `agent_type`, `response_format`, `get_prompt()` y, si los necesita, `get_tools()` y `get_middleware()`. `initialize()` construye el agente una sola vez y `process()` ejecuta un turno.
- **El modelo se elige desde fuera** (`model` + `settings`). `llm=` es la costura de tests.
- **La salida estructurada es opcional.** Con `response_format = MiModelo` el resultado llega en `AgentTurn.structured`; con `None`, en `AgentTurn.answer` como texto. Si se declara `response_format` y no llega, salta `AgentError(kind="NoStructuredResponse")`.
- **El agente no guarda estado.** Recibe `history` y devuelve `new_messages`; persistirlos es cosa de quien llama.
- **Datos de seguridad fuera del LLM.** El tenant viaja en `AgentContext` (`context=`). Las tools lo leen con `ToolRuntime` y el argumento `runtime` no aparece en el esquema que ve el LLM. Si falta el contexto, la tool falla cerrada.
- **Tools.** Una por archivo, sobre `AppTool`, con `name` y `description` explícitos y `args_schema` en Pydantic. Cualquier excepción llega al LLM como `SAFE_FAILURE`, sin el detalle interno.
- **Prompts como datos.** Van en YAML con `version`, sin Jinja ni `ChatPromptTemplate`, y el system prompt se pasa como string a `create_agent`.
- **Factory de LLM.** Importa los proveedores de forma perezosa (instala solo los que uses) y lanza `ValueError` ante un proveedor desconocido.

## Cómo adaptarla

1. Copia `files/` a la raíz del backend; si ya tienes `tests/` y `pytest.ini`, fusiónalos. Si `agentic/` va dentro de un paquete (`app/agentic/`), los imports relativos siguen funcionando. En los tests, cambia `from agentic...` por la ruta real.
2. Sustituye `{{app_name}}` en `prompts/*.yaml`.
3. Ajusta `AgentContext` a tu app y deja solo los proveedores y modelos que uses en `llm/models.py`.
4. **Nueva tool:** copia `tools/search_documents.py`, define `Args` con `runtime: ToolRuntime[AgentContext]` e implementa `execute()`. Regístrala en `ToolSet.default`.
5. **Nuevo agente:** crea una subclase de `BaseAgent` en `agents/agents.py` y, si devuelve datos, añade su modelo en `agents/models.py`. Crea su `prompts/<nombre>.<lang>.yaml`.
6. Instancia los agentes desde fuera de `agentic/`, con tus settings:

   ```python
   agent = AssistantAgent(LLMModel.GPT_4_1_MINI, LLMSettings(openai_api_key=...), language="es",
                          tools=ToolSet.default(document_search=my_service))
   turn = await agent.process("pregunta", context=AgentContext(tenant_id=..., user_id=...), history=[...])
   ```

**Dependencias** (probado con langchain 1.4.9, langgraph 1.2.20 y langchain-core 1.7.7):

```
langchain>=1.3
langgraph>=1.2
pydantic>=2.11
pyyaml
langchain-openai>=1.1      # OpenAI y Azure OpenAI
langchain-anthropic>=1.1   # opcional
langchain-groq>=1.1        # opcional
pytest, pytest-asyncio     # tests
```

Para comprobarla: `pytest` desde la carpeta copiada.

## Origen

- `BaseAgent` + `create_agent`, enum `LLMModel` + factory, `initialize()` y `process()`: aurora, ATI_PLATFORM y Vera-Symplia.
- `llm=` como costura de tests, `context_schema` con `extra="forbid"`, middleware `@wrap_model_call` creado por factory y prompts YAML por idioma: ATI_PLATFORM.
- `response_format` como atributo de clase, `get_tools()` y `get_middleware()`, tools sobre `BaseTool` con `ToolRuntime` y `ToolSet.default()`: Vera-Symplia.
- Proveedor Azure OpenAI: nuevo, no aparecía en ningún proyecto.
