"""Agentic layer of the app.

Settings: this package brings a config BLOCK (`llm/settings.py`, `LLMSettings`) that the project
settings inherit. It reads them through `get_llm_settings()`, the only place that knows where the
project settings live (`PROJECT_SETTINGS`), imported lazily.

Rule: nothing else under `agentic/` imports the app (DB, FastAPI, services).
Services are injected from the outside (see `registry.py`), so this package can be tested
on its own with fake LLMs.
"""
