# CopyPasta-Kitchen 🍝

Recetario de plantillas para que los agentes de código (Claude Code y similares) **no se inventen la estructura** de un proyecto, sino que partan de patrones ya probados.

Cuando un agente tenga que crear una API con FastAPI, un agente con LangGraph, un frontend, etc., consulta este recetario, carga **solo la receta que necesita** y la usa como referencia.

## Objetivo

- Reunir en un único sitio los patrones de proyectos reales ya desarrollados (aurora, rag_tool_upv, ATI_PLATFORM, Vera-Symplia…).
- Convertirlos en **recetas** reutilizables: backend, agentes, frontend, infraestructura, tests…
- Que un agente pueda **descubrir, leer y descargar** una receta sin tener que cargar el repositorio entero en su contexto.

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
2. [ ] Analizar los proyectos de origen → `analysis/<proyecto>.md`.
3. [ ] Convertir los patrones comunes en recetas.
4. [ ] Implementar la CLI `copypasta`.
5. [ ] (Opcional) Skill de Claude Code que envuelva la CLI.
