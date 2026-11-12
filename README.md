# CopyPasta-Kitchen 🍝

Recetario de plantillas para que los agentes de código (Claude Code y similares) **no se inventen la estructura** de un proyecto, sino que partan de patrones ya probados.

Cuando un agente tenga que crear una API con FastAPI, un agente con LangGraph, un frontend, etc., consulta este recetario, carga **solo la receta que necesita** y la usa como referencia.

## Objetivo

- Reunir en un único sitio los patrones de proyectos reales ya desarrollados (aurora, rag_tool_upv, ATI_PLATFORM, Vera-Symplia…).
- Convertirlos en **recetas** reutilizables: backend, agentes, frontend, infraestructura, tests…
- Que un agente pueda **descubrir, leer y descargar** una receta sin tener que cargar el repositorio entero en su contexto.

## Filosofía de las recetas

Las recetas siguen la forma de trabajar del autor, sobre todo en backend:

- **Factories.** Un único punto construye cada pieza intercambiable: el LLM, la memoria, la autenticación, el STT o el TTS. Un proveedor desconocido lanza un error explícito, nunca un valor por defecto silencioso.
- **Clases base y herencia.** Cada familia tiene una clase base abstracta (`BaseAgent`, `AppTool`, `Memory`…) y las implementaciones concretas solo declaran lo que las distingue.
- **Cambiar de proveedor sin tocar código.** El proveedor o el backend se eligen en los **settings** (`.env`): `ASSISTANT_MODEL=claude-sonnet-5-5` o `MEMORY_BACKEND=sql`. La factory lee el valor y construye la implementación. Cambiar de OpenAI a Anthropic, o de memoria en RAM a Postgres, es cambiar una variable.
- **Settings por bloques.** Hay un único `Settings` por proyecto y cada receta aporta su bloque, que ese `Settings` hereda.
- **Pydantic siempre.** Cualquier dato estructurado es un modelo Pydantic (`BaseModel`, `frozen=True` si es inmutable): se valida, se serializa y documenta sus campos. No hay `dataclass` en las recetas.
- **Costuras de test.** Todo se puede probar sin claves ni red: LLMs falsos, implementaciones en memoria e inyección por constructor.

## Recetas

### Disponibles

| id | Categoría | Para qué | Relación |
|---|---|---|---|
| `project-settings` | backend | `Settings` único del backend (pydantic-settings, `.env`), `get_settings()` y composición por bloques | — |
| `langchain-agent` | agents | Agente con `create_agent`: clase base, factory de LLM (OpenAI, Anthropic, Azure y Groq), tools, prompts YAML | usa `project-settings` |
| `agent-memory` | agents | Memoria de conversación: backend en settings (RAM o SQL), ventana por turnos, idempotente, tests de conformidad | usa `project-settings` |
| `langgraph-graph` | agents | Grafo de flujo fijo (router → agente \| rechazo) con salida en JSON o SSE | requiere `langchain-agent` y `agent-memory` |
| `auth-verifier` | backend | Quién llama a partir del token Bearer: Supabase (JWKS), JWT propio o doble de test, elegido en settings, con 401/503 y mapeo de claims en un método | usa `project-settings` |
| `agent-chat-api` | backend | Endpoints FastAPI del chat: `POST /agent/chat` (JSON) y `/agent/stream` (SSE), auth Bearer, guards (404/401/403/429) y `create_app` | requiere `langgraph-graph`, usa `project-settings`, `auth-verifier` |
| `conversation-history` | backend | Historial del chat: `GET /conversations` (lista paginada con título), `GET /conversations/{id}/messages` y `DELETE`, sobre la memoria de `agent-memory` | requiere `agent-chat-api` |
| `agent-feedback` | backend | Pulgares sobre las respuestas del agente: un voto por usuario y mensaje (upsert), comentario, deshacer y lista por conversación; backend RAM o SQL | requiere `agent-chat-api`, usa `project-settings` |
| `rate-limit-quota` | backend | Rate limit por usuario y cuota diaria/mensual por tenant: lógica en clases base, backend RAM o SQL por settings, 429 con `code` y `GET /agent/quota` | usa `project-settings`, `agent-chat-api` |
| `vite-react-base` | frontend | SPA Vite + React + TS para un backend Python: API intercambiable (http o fake) por configuración, cliente con auth y errores tipados | — |
| `react-agent-chat` | frontend | Chat con un agente en streaming SSE: tokens, tools, cancelar, errores, Markdown seguro | requiere `vite-react-base`, usa `agent-chat-api` |

`requires`: hay que copiar las dos recetas. `uses`: se integra con la otra receta, pero no la trae.

### Pendientes

Ver la hoja de ruta y `analysis/chat.md`. Todavía no existe receta de FastAPI genérica, auth, cuotas, historial de conversaciones, feedback ni RAG.

## Conceptos

| Concepto | Qué es |
|---|---|
| **Receta** | Una pieza reutilizable (p. ej. `fastapi-base`). Vive en `recipes/<categoría>/<id>/`. |
| `RECIPE.md` | Explica cuándo usar la receta, las decisiones que toma y cómo adaptarla. |
| `files/` | Los archivos de la plantilla, listos para copiar. |
| `catalog.yaml` | Índice de todas las recetas: id, categoría, descripción de una línea y tags. |
| `analysis/` | Notas de los patrones encontrados en cada proyecto de origen, antes de convertirse en recetas. |

## Estructura

```
CopyPasta-Kitchen/
├── README.md
├── AGENTS.md          # instrucciones para agentes que trabajan EN este repo
├── CLAUDE.md          # importa AGENTS.md para Claude Code
├── catalog.yaml       # índice de recetas
├── recipes/
│   ├── backend/
│   ├── agents/
│   └── frontend/
├── cli/               # CLI "copypasta" (pendiente)
└── analysis/          # análisis de los proyectos de origen
```

## Uso previsto (CLI, pendiente de implementar)

El flujo está pensado para gastar el mínimo contexto en cada paso:

```bash
# 1. Descubrir: solo ids y descripción corta
copypasta list --tag api

# 2. Leer: solo el RECIPE.md de una receta
copypasta show fastapi-base

# 3. Descargar: copia los archivos al proyecto
copypasta get fastapi-base --to ./backend
```

Sin instalación, vía `uvx`:

```bash
uvx --from git+https://github.com/damiangilgonzalez1995/CopyPasta-Kitchen copypasta list
```

### En otros proyectos

Añade esto al `AGENTS.md` (o `CLAUDE.md`) del proyecto donde trabaje el agente:

```markdown
## Plantillas
Antes de crear la estructura de una pieza nueva (API, agente, frontend…), ejecuta
`copypasta list` para ver si existe una receta. Si existe, léela con `copypasta show <id>`
y síguela en lugar de inventar una estructura.
```

## Hoja de ruta

1. [x] Definir objetivo y estructura (este README y `AGENTS.md`).
2. [ ] Analizar los proyectos de origen → `analysis/<proyecto>.md` (hecho: síntesis en `analysis/agentic-langgraph.md`, `analysis/frontend.md` y `analysis/chat.md`).
3. [ ] Convertir los patrones comunes en recetas:
   - [x] `project-settings`, `langchain-agent`, `agent-memory`, `langgraph-graph`, `agent-chat-api`, `rate-limit-quota`, `conversation-history`, `agent-feedback`, `auth-verifier`
   - [x] `vite-react-base`, `react-agent-chat`
   - [ ] `fastapi-base`: app, lifespan, routers, dependencias, request id, formato de error único
   - [ ] `rag-retriever`, `voice-providers` (STT/TTS), `observability`
   - [ ] Frontend: auth con Supabase (`TokenProvider`), router, e2e con Playwright contra el fake
4. [ ] Implementar la CLI `copypasta`.
5. [ ] (Opcional) Skill de Claude Code que envuelva la CLI.
