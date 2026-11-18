---
name: copypasta
description: Usa el recetario CopyPasta-Kitchen (CLI `copypasta`) antes de crear la estructura de cualquier pieza nueva de un proyecto: una API FastAPI, un agente LangChain o LangGraph, memoria de conversación, RAG, auth, rate limit, observabilidad, voz, settings, un frontend React, su login, su router o sus e2e. Úsala siempre que el usuario pida "crear", "montar", "añadir" o "empezar" una de esas piezas, mencione plantillas, recetas, "copypasta" o "la estructura que uso", o cuando estés a punto de inventar una estructura de carpetas, una factory o una clase base: casi seguro hay una receta ya probada.
---

# copypasta: recetas en lugar de estructuras inventadas

CopyPasta-Kitchen es un recetario de plantillas extraídas de proyectos reales. Cada receta trae `RECIPE.md` (cuándo usarla, decisiones, cómo adaptarla) y `files/` listos para copiar, con tests. La CLI `copypasta` está hecha para gastar el mínimo contexto: primero solo ids, luego una receta, luego los archivos. No clones ni leas el repositorio entero.

## Cómo ejecutar la CLI

Sin instalar nada, con `uv` (Python 3.11 a 3.14, `uv` elige el intérprete solo):

```bash
uvx --from git+https://github.com/damiangilgonzalez1995/CopyPasta-Kitchen copypasta <comando>
```

Si el checkout de CopyPasta-Kitchen está en el disco (por ejemplo como repo hermano en `../CopyPasta-Kitchen`), vale `uvx --from ../CopyPasta-Kitchen copypasta <comando>`, que además refleja cambios locales. Si `uvx` no existe, díselo al usuario: `pip install uv` o `pipx install uv`.

## Flujo

1. **Descubrir.** `copypasta list` (o `--tag api`, `--category frontend`, `--json`). Devuelve una línea por receta y marca `[requiere ...]`. Elige por la descripción, no por el nombre.
2. **Leer.** `copypasta show <id>`. Es el `RECIPE.md` completo: lee "Cuándo usarla" para confirmar que encaja, "Decisiones" para no deshacerlas sin motivo y "Cómo adaptarla" para los pasos tras copiar. `copypasta show <id> --files` lista los archivos sin leerlos.
3. **Copiar.** `copypasta get <id> --to <carpeta> --with-requires`. Copia `files/` dentro de la carpeta destino (la raíz del backend o del frontend, no una subcarpeta nueva salvo que la receta lo diga). Nunca pisa un archivo que ya exista: si avisa "ya existía, no se toca", decide a mano qué conservar; `--force` solo cuando el usuario lo confirme. Varias recetas traen `pytest.ini` y `tests/__init__.py`: quédate con el `pytest.ini` más completo (el de `fastapi-base` lleva `asyncio_mode = auto`, que los tests async necesitan). Al final imprime qué requiere, con qué se integra y los marcadores `{{...}}` que hay que sustituir.
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

Solo cuando estés trabajando **dentro** del repositorio CopyPasta-Kitchen: sigue su `AGENTS.md` y ejecuta `copypasta check` antes de confirmar cambios (valida `catalog.yaml` contra `recipes/`).
