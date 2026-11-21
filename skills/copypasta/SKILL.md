---
name: copypasta
description: "Use before creating the structure of any new piece of a project — a FastAPI API, a LangChain or LangGraph agent, conversation memory, RAG, auth, rate limit, observability, voice, settings, a React frontend, its login, router or e2e — or when the user asks which templates or recipes exist, wants to bring one in, or mentions 'copypasta', 'plantillas', 'recetas' or 'la estructura que uso'. Lists the CopyPasta-Kitchen recipes and copies only the one that is needed. NOT how to write FastAPI code itself (that is `fastapi`), NOT agent design decisions (that is `building-agents`)."
tags: [templates, recipes, scaffolding, copypasta, fastapi, langgraph, react]
recommends: [fastapi, building-agents, react]
profiles: [minimal, core, ui, full]
origin: damiangil
---

# copypasta: recetas en lugar de estructuras inventadas

CopyPasta-Kitchen es un recetario de plantillas extraídas de proyectos reales. Cada receta trae `RECIPE.md` (cuándo usarla, decisiones, cómo adaptarla) y `files/` listos para copiar, con tests. La CLI está hecha para gastar el mínimo contexto: primero solo ids, luego una receta, luego los archivos. No clones ni leas el repositorio entero.

## Cómo ejecutar la CLI

Con el harness instalado, el recetario va dentro, en la versión con la que se probó esa versión del harness. No hay que instalar nada más:

```bash
npx @damiangilgonzalez/harness recipes <comando>
```

Sin el harness, el mismo recetario es un paquete npm por sí solo (Node 18.3 o superior), con los mismos comandos:

```bash
npx @damiangilgonzalez/copypasta <comando>
```

Abajo se escribe `recipes <comando>`; ponle delante la forma que toque. Si estás **dentro** del checkout de CopyPasta-Kitchen trabajando en las recetas, usa `node cli/copypasta.js <comando>`, que lee los cambios locales en lugar de la versión publicada.

## Flujo

1. **Descubrir.** `recipes list` (o `--tag api`, `--category frontend`, `--json`). Devuelve una línea por receta y marca `[requiere ...]`. Elige por la descripción, no por el nombre. Si el usuario solo preguntó qué plantillas hay, enséñale esa lista y para aquí.
2. **Leer.** `recipes show <id>`. Es el `RECIPE.md` completo: lee "Cuándo usarla" para confirmar que encaja, "Decisiones" para no deshacerlas sin motivo y "Cómo adaptarla" para los pasos tras copiar. `recipes show <id> --files` lista los archivos sin leerlos.
3. **Copiar.** `recipes get <id> --to <carpeta> --with-requires`. Copia `files/` dentro de la carpeta destino (la raíz del backend o del frontend, no una subcarpeta nueva salvo que la receta lo diga). Nunca pisa un archivo que ya exista: si avisa "ya existía, no se toca", decide a mano qué conservar; `--force` solo cuando el usuario lo confirme. Varias recetas traen `pytest.ini` y `tests/__init__.py`: quédate con el `pytest.ini` más completo (el de `fastapi-base` lleva `asyncio_mode = auto`, que los tests async necesitan). Al final imprime qué requiere, con qué se integra y los marcadores `{{...}}` que hay que sustituir.
4. **Adaptar.** Sustituye los marcadores (`{{app_name}}` y los que diga), sigue los pasos numerados de "Cómo adaptarla" (settings que se mezclan en el `Settings` del proyecto, `include_router`, arranque en `main.tsx`...) y ejecuta los tests que trae la receta antes de tocar nada más. Si el proyecto ya tiene una pieza equivalente (otro `Settings`, otro `create_app`), integra la receta en ella en vez de duplicarla.

Si `list` no tiene nada que encaje, dilo y construye la pieza siguiendo las mismas reglas de las recetas (abajo); no busques "algo parecido" y lo fuerces.

## Reglas que las recetas dan por hechas

Mantenlas en lo que añadas encima, porque el proyecto se lee como una pieza:

- **Por capacidad, no por capas.** Una carpeta por cosa que hace el sistema (`rag/`, `auth/`, `limits/`), con su contrato `base.py`, un fichero por proveedor, `factory.py`, `settings.py` y su doble de test dentro. Las capacidades no se importan entre sí; quien las combina está un nivel por encima (`create_app`, `main.py`, `main.tsx`).
- **El proveedor se elige en `.env`**, sin valor por defecto silencioso: la factory hace `match` sobre un Enum y un valor desconocido falla nombrándolo. Con un solo proveedor y sin doble de test no hay clase base ni factory.
- **Pydantic siempre** en Python: `BaseModel` (y `ConfigDict(frozen=True)` si es inmutable) para todo dato estructurado; nunca `@dataclass`, `NamedTuple` ni `TypedDict`.
- **Costuras de test:** todo se prueba sin claves ni red (dobles, `httpx.MockTransport`, fakes en memoria). Si añades un proveedor, pásalo por la batería de conformidad de la receta.
- Código e identificadores en inglés; documentación para el usuario en su idioma.

## Qué decirle al usuario

Di qué receta has usado y por qué, qué archivos se han copiado y qué quedó sin copiar por existir ya, qué marcadores sustituiste y qué pasos de "Cómo adaptarla" hiciste o dejaste pendientes (por ejemplo, una clave en `.env` que solo el usuario puede poner). Si cambiaste una decisión de la receta, nómbrala.

## Mantener el recetario

Solo cuando estés trabajando **dentro** del repositorio CopyPasta-Kitchen: sigue su `AGENTS.md` y ejecuta `npm run check` antes de confirmar cambios (valida `catalog.yaml` contra `recipes/`).

Esta skill vive en dos sitios, byte a byte iguales: `skills/copypasta/SKILL.md` de CopyPasta-Kitchen y la misma ruta en el harness (`@damiangilgonzalez/harness`). Un cambio en una copia se lleva a la otra en la misma tanda; el test `tests/copypasta-skill-sync.test.js` del harness lo vigila cuando los dos repos están en el disco.
