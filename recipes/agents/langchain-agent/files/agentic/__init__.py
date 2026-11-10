"""Agentic layer of the app.

Rule: nothing under `agentic/` imports the app (settings singletons, DB, FastAPI).
The app wires it from the outside (see `registry.py`): settings, services and
caches are injected, so this package can be tested on its own with fake LLMs.
"""
