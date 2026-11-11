# langchain-agent

## Cuándo usarla

Cuando necesites **un agente LLM**, con o sin tools, construido con `langchain.agents.create_agent` (LangChain v1). Sirve sola o como pieza de un nodo de grafo (receta `langgraph-graph`).

No la uses para cadenas de una sola llamada sin agente (`prompt | model`). Tampoco para pipelines deterministas: para eso, un grafo sin agente.

**Usa la receta `project-settings`, pero no la trae.** Necesita que el proyecto tenga un `Settings` con `get_settings()`, ya sea el de esa receta o el que tenga ya el backend, y le añade su bloque `LLMSettings` por herencia. Sin él, los tests funcionan igual. Solo falla `get_llm_settings()`, y lo hace con un mensaje que dice qué falta.

## Qué incluye

```
agentic/
  __init__.py            regla: agentic/ no importa nada de la app (salvo get_llm_settings, perezoso)
  context.py             AgentContext (tenant, user, idioma): lo leen tools y middleware, nunca el LLM
  llm/
    models.py            enum LLMModel(provider, model_id, reasoning_effort) + LLMProviderName
    settings.py          bloque LLMSettings(BaseSettings) para heredar en el Settings del proyecto + get_llm_settings()
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
  test_agents.py         19 tests, sin API keys
pytest.ini
```

## Decisiones

- **`create_agent` y no `create_react_agent`**: es la API de LangChain v1 y admite `middleware`, `response_format` y `context_schema`.
- **Clase base con plantilla.** Una subclase solo declara lo que la distingue: `agent_type`, `response_format`, `get_prompt()` y, si los necesita, `get_tools()` y `get_middleware()`. `initialize()` construye el agente una sola vez y `process()` ejecuta un turno.
- **Settings por bloques.** La receta no trae settings propios del proyecto. Trae el bloque `LLMSettings` (claves, timeouts y modelo de cada agente), y el `Settings` del proyecto lo hereda: `class Settings(LLMSettings, BaseAppSettings)`. Es el patrón de ATI_PLATFORM con `Settings(ObservabilitySettings)`. La factory lo lee sola con `get_llm_settings()`, así que nadie pasa las claves a mano. `settings=` solo se usa en tests.
- **Una sola línea acopla la receta al proyecto:** `PROJECT_SETTINGS = "core.config"` en `llm/settings.py`. Se importa de forma perezosa, así que copiar la receta sola nunca rompe al importar.
- **El modelo se elige desde fuera**, por id en el `.env` (`ASSISTANT_MODEL=gpt-4.1-mini` → `LLMModel.from_id`). `llm=` es la costura de tests.
- **La salida estructurada es opcional.** Con `response_format = MiModelo` el resultado llega en `AgentTurn.structured`; con `None`, en `AgentTurn.answer` como texto. Si se declara `response_format` y no llega, salta `AgentError(kind="NoStructuredResponse")`.
- **El agente no guarda estado.** Recibe `history` y devuelve `new_messages`; persistirlos es cosa de quien llama.
- **Datos de seguridad fuera del LLM.** El tenant viaja en `AgentContext` (`context=`). Las tools lo leen con `ToolRuntime` y el argumento `runtime` no aparece en el esquema que ve el LLM. Si falta el contexto, la tool falla cerrada.
- **Tools.** Una por archivo, sobre `AppTool`, con `name` y `description` explícitos y `args_schema` en Pydantic. Cualquier excepción llega al LLM como `SAFE_FAILURE`, sin el detalle interno.
- **Prompts como datos.** Van en YAML con `version`, sin Jinja ni `ChatPromptTemplate`, y el system prompt se pasa como string a `create_agent`.
- **Factory de LLM.** Importa los proveedores de forma perezosa (instala solo los que uses) y lanza `ValueError` ante un proveedor desconocido.

## Cómo adaptarla

1. Copia `files/` a la raíz del backend; si ya tienes `tests/` y `pytest.ini`, fusiónalos. Si `agentic/` va dentro de un paquete (`app/agentic/`), los imports relativos siguen funcionando. En los tests, cambia `from agentic...` por la ruta real.
2. **Settings:** si el proyecto no tiene `Settings`, copia la receta `project-settings`. Después, en tu `Settings`:

   ```python
   from agentic.llm.settings import LLMSettings

   class Settings(LLMSettings, BaseAppSettings): ...
   ```

   Si tu módulo de settings no es `core.config`, cambia `PROJECT_SETTINGS` en `agentic/llm/settings.py`. Añade al `.env` las variables que aparecen en el docstring de ese archivo (`OPENAI_API_KEY`, `ASSISTANT_MODEL`, …).
3. Sustituye `{{app_name}}` en `prompts/*.yaml`.
4. Ajusta `AgentContext` a tu app y deja solo los proveedores y modelos que uses en `llm/models.py`.
5. **Nueva tool:** copia `tools/search_documents.py`, define `Args` con `runtime: ToolRuntime[AgentContext]` e implementa `execute()`. Regístrala en `ToolSet.default`.
6. **Nuevo agente:** crea una subclase de `BaseAgent` en `agents/agents.py` y, si devuelve datos, añade su modelo en `agents/models.py`. Crea su `prompts/<nombre>.<lang>.yaml` y su campo `<nombre>_model` en `Settings`.
7. Instancia los agentes. Las claves salen solas del `.env`:

   ```python
   settings = get_llm_settings()
   agent = AssistantAgent(LLMModel.from_id(settings.assistant_model), language="es",
                          tools=ToolSet.default(document_search=my_service))
   turn = await agent.process("pregunta", context=AgentContext(tenant_id=..., user_id=...), history=[...])
   ```

**Dependencias** (probado con langchain 1.4.9, langgraph 1.2.20 y langchain-core 1.7.7):

```
langchain>=1.3
langgraph>=1.2
pydantic>=2.11
pydantic-settings>=2.6     # para el bloque LLMSettings
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
- Bloque de settings heredado por el `Settings` del proyecto: ATI_PLATFORM (`Settings(ObservabilitySettings)`). `api_key_for(provider)`: Vera-Symplia, y aurora con `get_api_key`.
- Proveedor Azure OpenAI: nuevo, no aparecía en ningún proyecto.
