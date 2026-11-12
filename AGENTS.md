# AGENTS.md

Instrucciones para agentes que trabajan **dentro de este repositorio**. El objetivo del proyecto está en [README.md](README.md).

## Qué es este repo

Un recetario de plantillas (recetas) que otros agentes consultan para no inventarse estructuras. Aquí se crean y mantienen esas recetas.

## Reglas

### Recetas

- Cada receta vive en `recipes/<categoría>/<id>/` y contiene:
  - `RECIPE.md`: obligatorio.
  - `files/`: los archivos de la plantilla.
- El `id` es único, en kebab-case (`fastapi-base`, `langgraph-agent`).
- Toda receta nueva o modificada **debe** reflejarse en `catalog.yaml`.
- La `description` del catálogo es **una sola línea** y dice para qué sirve, no cómo está hecha. Es lo único que verá un agente al listar.

### Formato de `RECIPE.md`

```markdown
# <id>

## Cuándo usarla
## Qué incluye           (árbol de archivos de files/)
## Decisiones            (por qué esta estructura, librerías elegidas)
## Cómo adaptarla        (qué renombrar, variables, pasos tras copiar)
## Origen                (proyectos de los que se extrajo el patrón)
```

- Breve y accionable: es lo que el agente consumidor carga en contexto.
- Sin secretos, credenciales, URLs internas ni datos de clientes.

### Plantillas (`files/`)

- Código genérico: sin nombres de negocio de los proyectos de origen.
- Marcadores con el formato `{{nombre_variable}}` cuando haya que personalizar algo.
- Deben funcionar tras copiarlas y sustituir los marcadores (incluir dependencias y config mínima).
- **Python: Pydantic siempre.** Todo dato estructurado (estado, eventos, resultados, value objects, settings) es un `BaseModel`; para inmutabilidad, `ConfigDict(frozen=True)`. Nunca `@dataclass`, `NamedTuple` ni `TypedDict` como sustituto.

### Análisis (`analysis/`)

- Un archivo por proyecto de origen: `analysis/<proyecto>.md`.
- Los proyectos de origen están clonados como repos hermanos en `../` (`../aurora`, `../rag_tool_upv`, `../ATI_PLATFORM`, `../Vera-Symplia`). **Solo lectura**: nunca modificarlos.
- Registrar patrones observados, no copiar código propietario tal cual. Un patrón pasa a receta cuando aparece en más de un proyecto o es claramente reutilizable.
- No inventar: si algo no está claro en el código de origen, anotarlo como duda.

## Idioma

Documentación en español. Código, nombres de archivos e identificadores en inglés.
