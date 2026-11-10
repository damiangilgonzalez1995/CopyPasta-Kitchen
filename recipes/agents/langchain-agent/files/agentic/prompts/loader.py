"""Prompts as versioned data: `prompts/<name>.<language>.yaml`.

File format:

    name: assistant
    version: 1            # bump on every change; it is logged with each run
    language: es
    description: One line on what this prompt is for.
    system: |
      The system prompt text. Placeholders use str.format: {tenant_name}

Rules:
- One file per prompt and language. Missing language -> falls back to DEFAULT_LANGUAGE with a warning.
- No Jinja, no ChatPromptTemplate: the system prompt is a plain string passed to `create_agent`.
- Wrap data you inject in XML tags (<question>...</question>) so the model tells data from instructions.
"""

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent
DEFAULT_LANGUAGE = "es"
_REQUIRED = ("name", "version", "language", "system")


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    language: str
    description: str
    system: str

    def render(self, **values: str) -> str:
        """`system` with its `{placeholders}` filled. A missing value raises KeyError."""
        return self.system.format(**values) if values else self.system


@lru_cache(maxsize=None)
def load_prompt(name: str, language: str = DEFAULT_LANGUAGE) -> Prompt:
    """Load and cache a prompt. Names must be identifiers (guards against path traversal)."""
    if not name.isidentifier() or not language.isalpha():
        raise ValueError(f"Invalid prompt name or language: {name!r}, {language!r}")

    path = PROMPTS_DIR / f"{name}.{language}.yaml"
    if not path.exists():
        if language == DEFAULT_LANGUAGE:
            raise FileNotFoundError(f"Prompt not found: {path.name}")
        logger.warning("Prompt %s has no %r version; using %r", name, language, DEFAULT_LANGUAGE)
        return load_prompt(name, DEFAULT_LANGUAGE)

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    missing = [key for key in _REQUIRED if key not in data]
    if missing:
        raise ValueError(f"Prompt {path.name} is missing fields: {missing}")
    return Prompt(
        name=data["name"],
        version=int(data["version"]),
        language=data["language"],
        description=data.get("description", ""),
        system=data["system"],
    )
