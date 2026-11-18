"""The catalog: `catalog.yaml` parsed into Pydantic models, plus where the recipes live on disk.

Two layouts are supported, same code:
- the repo checkout (`catalog.yaml` and `recipes/` at the root, two levels above this package);
- the installed package (`uvx --from git+...`), where the build copies both next to this file.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class Recipe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    category: str
    description: str
    tags: tuple[str, ...] = ()
    path: str
    requires: tuple[str, ...] = ()
    uses: tuple[str, ...] = ()

    @field_validator("id")
    @classmethod
    def _kebab(cls, value: str) -> str:
        if not ID_PATTERN.match(value):
            raise ValueError(f"id must be kebab-case: {value!r}")
        return value

    @field_validator("description")
    @classmethod
    def _one_line(cls, value: str) -> str:
        if "\n" in value.strip():
            raise ValueError("description must be one line")
        return value.strip()


class Catalog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    recipes: tuple[Recipe, ...] = Field(default=())

    def get(self, recipe_id: str) -> Recipe:
        for recipe in self.recipes:
            if recipe.id == recipe_id:
                return recipe
        raise KeyError(recipe_id)

    def ids(self) -> set[str]:
        return {recipe.id for recipe in self.recipes}

    def filter(self, *, tag: str | None = None, category: str | None = None) -> tuple[Recipe, ...]:
        return tuple(
            recipe
            for recipe in self.recipes
            if (tag is None or tag in recipe.tags) and (category is None or recipe.category == category)
        )

    def closure(self, recipe_id: str) -> tuple[Recipe, ...]:
        """The recipe and everything it `requires`, transitively, dependencies first."""
        ordered: list[Recipe] = []

        def visit(current: str, trail: tuple[str, ...]) -> None:
            if current in trail:
                raise ValueError(f"requires cycle: {' -> '.join(trail + (current,))}")
            recipe = self.get(current)
            for dependency in recipe.requires:
                visit(dependency, trail + (current,))
            if recipe not in ordered:
                ordered.append(recipe)

        visit(recipe_id, ())
        return tuple(ordered)


class Kitchen(BaseModel):
    """A catalog bound to the directory that holds `catalog.yaml` and `recipes/`."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    root: Path
    catalog: Catalog

    def recipe_dir(self, recipe: Recipe) -> Path:
        return self.root / recipe.path

    def recipe_md(self, recipe: Recipe) -> Path:
        return self.recipe_dir(recipe) / "RECIPE.md"

    def files_dir(self, recipe: Recipe) -> Path:
        return self.recipe_dir(recipe) / "files"


def find_root(start: Path | None = None) -> Path:
    """The installed package first (it carries its own copy), then the checkout, then `start` upwards."""
    package = Path(__file__).resolve().parent
    candidates = [package, package.parent.parent]
    if start is not None:
        candidates.extend([start.resolve(), *start.resolve().parents])
    for candidate in candidates:
        if (candidate / "catalog.yaml").is_file() and (candidate / "recipes").is_dir():
            return candidate
    raise FileNotFoundError("catalog.yaml not found: run inside the CopyPasta-Kitchen checkout or install the package")


def load_catalog(path: Path) -> Catalog:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Catalog.model_validate(data)


def open_kitchen(root: Path | None = None) -> Kitchen:
    root = root or find_root(Path.cwd())
    return Kitchen(root=root, catalog=load_catalog(root / "catalog.yaml"))
