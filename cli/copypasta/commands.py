"""What each command does, without printing: `main.py` only formats. Tested directly."""

from __future__ import annotations

import shutil
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .catalog import Kitchen, Recipe

PLACEHOLDER = "{{"


class CopyResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    recipe_id: str
    copied: tuple[str, ...]
    skipped: tuple[str, ...]  # already existed and --force was not given
    requires: tuple[str, ...]
    uses: tuple[str, ...]


class Problem(BaseModel):
    model_config = ConfigDict(frozen=True)

    recipe_id: str | None
    message: str

    def __str__(self) -> str:
        return f"{self.recipe_id or 'catalog'}: {self.message}"


def list_recipes(kitchen: Kitchen, *, tag: str | None = None, category: str | None = None) -> tuple[Recipe, ...]:
    return kitchen.catalog.filter(tag=tag, category=category)


def show_recipe(kitchen: Kitchen, recipe_id: str) -> str:
    recipe = kitchen.catalog.get(recipe_id)
    return kitchen.recipe_md(recipe).read_text(encoding="utf-8")


def recipe_files(kitchen: Kitchen, recipe_id: str) -> tuple[str, ...]:
    """Relative paths of `files/`, sorted, with `/` separators."""
    files_dir = kitchen.files_dir(kitchen.catalog.get(recipe_id))
    if not files_dir.is_dir():
        return ()
    return tuple(sorted(path.relative_to(files_dir).as_posix() for path in files_dir.rglob("*") if path.is_file()))


def get_recipe(kitchen: Kitchen, recipe_id: str, destination: Path, *, force: bool = False, with_requires: bool = False) -> tuple[CopyResult, ...]:
    """Copies `files/` of the recipe (and of what it `requires`, if asked) into `destination`.

    Existing files are never overwritten unless `force`: a template must not clobber the project's own code.
    The exception is a file this same run just copied from a required recipe: a recipe that `requires` another
    may replace its files (react-app-router replaces App.tsx of vite-react-base).
    """
    recipes = kitchen.catalog.closure(recipe_id) if with_requires else (kitchen.catalog.get(recipe_id),)
    results = []
    written_now: set[Path] = set()
    for recipe in recipes:
        copied: list[str] = []
        skipped: list[str] = []
        files_dir = kitchen.files_dir(recipe)
        for relative in recipe_files(kitchen, recipe.id):
            source = files_dir / relative
            target = destination / relative
            if target.exists() and not force and target not in written_now:
                skipped.append(relative)
                continue
            written_now.add(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(relative)
        results.append(CopyResult(recipe_id=recipe.id, copied=tuple(copied), skipped=tuple(skipped), requires=recipe.requires, uses=recipe.uses))
    return tuple(results)


def placeholders(kitchen: Kitchen, recipe_id: str) -> tuple[str, ...]:
    """`{{name}}` markers found in the recipe files: what the consumer has to replace after copying."""
    import re

    pattern = re.compile(r"\{\{([a-z_][a-z0-9_]*)\}\}")
    files_dir = kitchen.files_dir(kitchen.catalog.get(recipe_id))
    found: set[str] = set()
    for relative in recipe_files(kitchen, recipe_id):
        try:
            found.update(pattern.findall((files_dir / relative).read_text(encoding="utf-8")))
        except UnicodeDecodeError:
            continue  # binary file (an image, a font)
    return tuple(sorted(found))


def check(kitchen: Kitchen) -> tuple[Problem, ...]:
    """The rules of AGENTS.md: every recipe on disk is in the catalog, every entry exists with RECIPE.md and files/,
    ids are unique, `requires`/`uses` point to real recipes, no self-reference, no `requires` cycle."""
    problems: list[Problem] = []
    catalog = kitchen.catalog
    ids = catalog.ids()

    seen: set[str] = set()
    for recipe in catalog.recipes:
        if recipe.id in seen:
            problems.append(Problem(recipe_id=recipe.id, message="duplicate id"))
        seen.add(recipe.id)

        expected = f"recipes/{recipe.category}/{recipe.id}"
        if recipe.path != expected:
            problems.append(Problem(recipe_id=recipe.id, message=f"path is {recipe.path!r}, expected {expected!r}"))
        if not kitchen.recipe_md(recipe).is_file():
            problems.append(Problem(recipe_id=recipe.id, message="RECIPE.md missing"))
        elif not kitchen.recipe_md(recipe).read_text(encoding="utf-8").lstrip().startswith(f"# {recipe.id}"):
            problems.append(Problem(recipe_id=recipe.id, message=f"RECIPE.md must start with '# {recipe.id}'"))
        if not recipe_files(kitchen, recipe.id):
            problems.append(Problem(recipe_id=recipe.id, message="files/ missing or empty"))
        if not recipe.tags:
            problems.append(Problem(recipe_id=recipe.id, message="no tags"))
        for field in ("requires", "uses"):
            for other in getattr(recipe, field):
                if other == recipe.id:
                    problems.append(Problem(recipe_id=recipe.id, message=f"{field} itself"))
                elif other not in ids:
                    problems.append(Problem(recipe_id=recipe.id, message=f"{field} unknown recipe {other!r}"))
        try:
            catalog.closure(recipe.id)
        except (ValueError, KeyError) as error:
            problems.append(Problem(recipe_id=recipe.id, message=str(error)))

    recipes_dir = kitchen.root / "recipes"
    on_disk = {
        f"recipes/{folder.parent.name}/{folder.name}"
        for folder in recipes_dir.glob("*/*")
        if folder.is_dir() and not folder.name.startswith(".")
    }
    for path in sorted(on_disk - {recipe.path for recipe in catalog.recipes}):
        problems.append(Problem(recipe_id=None, message=f"{path} exists on disk but is not in catalog.yaml"))
    return tuple(problems)
