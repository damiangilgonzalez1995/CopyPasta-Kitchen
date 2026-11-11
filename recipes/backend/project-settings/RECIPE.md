# project-settings

## Cuándo usarla

Cuando un backend en Python necesite **una sola configuración para todo el proyecto**, cargada desde variables de entorno y `.env`. Es la base sobre la que otras recetas añaden su bloque. Por ejemplo, `langchain-agent` añade `LLMSettings`.

No depende de ninguna otra receta.

## Qué incluye

```
core/
  config.py        BaseAppSettings (campos comunes) + Settings (compone bloques) + get_settings() en caché
.env.example       variables base; cada bloque añade las suyas
tests/
  test_settings.py 4 tests sobre BaseAppSettings: env > defaults, caché, composición, valores explícitos > env
pytest.ini
```

## Decisiones

- **Un único `Settings` por proyecto**, en la raíz del backend (`core/config.py`), al lado de `api/`, `db/` y `agentic/`. Nadie lee `os.environ` directamente.
- **pydantic-settings.** Las variables de entorno no distinguen mayúsculas (`APP_NAME` → `app_name`) y tienen prioridad sobre el `.env`. Con `extra="ignore"`, las variables que sobran no rompen nada.
- **`get_settings()` con `lru_cache`.** Se carga una vez. En tests: `get_settings.cache_clear()` o `Settings(_env_file=None, ...)`.
- **Composición por bloques.** Cada módulo con configuración propia trae su `BaseSettings` y `Settings` lo hereda: `class Settings(LLMSettings, ObservabilitySettings, BaseAppSettings)`. Esta receta no conoce esos bloques. Son ellos los que hacen referencia a esta.
- **Secretos en `SecretStr`**, para que no salgan en los logs ni en el `repr`.

## Cómo adaptarla

1. Copia `files/` a la raíz del backend. Si `core/` va dentro de un paquete (`app/core/`), cambia los imports de los tests.
2. Sustituye `{{app_name}}` en `core/config.py` y `.env.example`.
3. `cp .env.example .env`. No subas el `.env` a git: añádelo a `.gitignore`.
4. **Añadir un bloque de otra receta:** impórtalo en `core/config.py` y ponlo como padre de `Settings`, delante de `BaseAppSettings`. Añade al `.env` sus variables, que vienen en el RECIPE.md de esa receta.
5. Para usarlo: `from core.config import get_settings`; `get_settings().environment`.

**Dependencias:** `pydantic-settings>=2.6` y `pytest` para los tests.

## Origen

- `Settings(BaseSettings)` con `.env` en la raíz del backend: los cuatro proyectos (ATI_PLATFORM en `app/core/config.py`, aurora y Vera-Symplia en `config/settings.py`, rag_tool_upv en `core/settings.py`).
- `get_settings()` con `lru_cache`: aurora. Singleton de módulo: ATI_PLATFORM y rag_tool_upv.
- Composición heredando bloques (`Settings(ObservabilitySettings)`): ATI_PLATFORM.
