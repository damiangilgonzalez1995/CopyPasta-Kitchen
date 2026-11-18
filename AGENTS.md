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
- Antes de confirmar cambios, ejecuta `copypasta check` (o `python -m copypasta.main check` desde `cli/`): comprueba que cada receta del disco está en el catálogo, que cada entrada tiene `RECIPE.md` y `files/`, y que `requires`/`uses` apuntan a recetas reales.
- La `description` del catálogo es **una sola línea** y dice para qué sirve, no cómo está hecha. Es lo único que verá un agente al listar.

### Formato de `RECIPE.md`

```markdown
# <id>

## Cuándo usarla
## Qué incluye           (árbol de archivos de files/)
## Decisiones            (por qué esta estructura, librerías elegidas)
## Cómo adaptarla        (qué renombrar, variables, pasos tras copiar)
## Origen                (qué está probado en producción y qué es nuevo en la receta)
```

- Breve y accionable: es lo que el agente consumidor carga en contexto.
- Sin secretos, credenciales, URLs internas ni datos de clientes.

### Plantillas (`files/`)

- Código genérico: sin nombres de negocio, clientes ni productos.
- Marcadores con el formato `{{nombre_variable}}` cuando haya que personalizar algo.
- Deben funcionar tras copiarlas y sustituir los marcadores (incluir dependencias y config mínima).
- **Estructura por capacidad** (ver "Cómo se estructura un proyecto" en el README): cada receta es una carpeta con su contrato (`base.py`, ABC), un fichero por proveedor, `factory.py` con `match` sobre un Enum de settings e import perezoso, `settings.py` como bloque y su doble de test. Las capacidades no se importan entre sí; quien las combina está un nivel por encima (`create_app`, `main.py`).
- **Python: Pydantic siempre.** Todo dato estructurado (estado, eventos, resultados, value objects, settings) es un `BaseModel`; para inmutabilidad, `ConfigDict(frozen=True)`. Nunca `@dataclass`, `NamedTuple` ni `TypedDict` como sustituto.

### Sin referencias a proyectos anteriores

- El repositorio **no menciona ningún proyecto anterior del autor**: ni nombres de proyectos, empresas, clientes o productos, ni rutas de archivos de otros repos. Los patrones se presentan como "probado en producción" o "nuevo en esta receta", sin decir de dónde salen.
- Registrar patrones, no copiar código propietario tal cual. Un patrón pasa a receta cuando es claramente reutilizable.
- No inventar: si algo no está claro, anotarlo como duda.

## Idioma

Documentación en español. Código, nombres de archivos e identificadores en inglés.
