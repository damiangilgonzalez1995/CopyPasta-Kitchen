"""The CLI against the real catalog (so a broken recipe fails here too) and against a tiny kitchen in tmp."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from copypasta import commands
from copypasta.catalog import Catalog, Kitchen, find_root, open_kitchen
from copypasta.main import main

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def real() -> Kitchen:
    return open_kitchen(REPO)


@pytest.fixture
def tiny(tmp_path: Path) -> Kitchen:
    """base <- child (requires base, replaces one of its files); loose uses child."""
    (tmp_path / "catalog.yaml").write_text(
        """
recipes:
  - id: base
    category: backend
    description: la base
    tags: [api]
    path: recipes/backend/base
  - id: child
    category: backend
    description: encima de la base
    tags: [api, extra]
    path: recipes/backend/child
    requires: [base]
    uses: [loose]
  - id: loose
    category: frontend
    description: aparte
    tags: [web]
    path: recipes/frontend/loose
""",
        encoding="utf-8",
    )
    for recipe, files in {
        "backend/base": {"app.py": "name = '{{app_name}}'\n", "shared.py": "base\n"},
        "backend/child": {"shared.py": "child\n", "extra/x.py": "x\n"},
        "frontend/loose": {"index.html": "<h1>{{app_name}}</h1>"},
    }.items():
        folder = tmp_path / "recipes" / recipe
        (folder / "files").mkdir(parents=True)
        (folder / "RECIPE.md").write_text(f"# {recipe.split('/')[1]}\n\n## Cuándo usarla\n", encoding="utf-8")
        for name, content in files.items():
            target = folder / "files" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    return open_kitchen(tmp_path)


# --- the real catalog -----------------------------------------------------------------------


def test_real_catalog_passes_check(real: Kitchen):
    assert commands.check(real) == ()
    assert len(real.catalog.recipes) >= 18


def test_every_real_recipe_shows_and_lists_files(real: Kitchen):
    for recipe in real.catalog.recipes:
        assert commands.show_recipe(real, recipe.id).startswith(f"# {recipe.id}")
        assert commands.recipe_files(real, recipe.id)


def test_find_root_from_a_subfolder():
    assert find_root(REPO / "recipes" / "backend") == REPO


# --- commands on the tiny kitchen -------------------------------------------------------------


def test_list_filters_by_tag_and_category(tiny: Kitchen):
    assert [r.id for r in commands.list_recipes(tiny)] == ["base", "child", "loose"]
    assert [r.id for r in commands.list_recipes(tiny, tag="extra")] == ["child"]
    assert [r.id for r in commands.list_recipes(tiny, category="frontend")] == ["loose"]


def test_get_copies_files_and_never_overwrites_the_project(tiny: Kitchen, tmp_path: Path):
    dest = tmp_path / "project"
    (dest / "app.py").parent.mkdir()
    (dest / "app.py").write_text("mine\n", encoding="utf-8")

    (result,) = commands.get_recipe(tiny, "base", dest)
    assert result.copied == ("shared.py",) and result.skipped == ("app.py",)
    assert (dest / "app.py").read_text(encoding="utf-8") == "mine\n"

    (forced,) = commands.get_recipe(tiny, "base", dest, force=True)
    assert forced.skipped == () and (dest / "app.py").read_text(encoding="utf-8").startswith("name")


def test_get_with_requires_copies_dependencies_first_and_lets_the_child_replace_them(tiny: Kitchen, tmp_path: Path):
    dest = tmp_path / "project"
    results = commands.get_recipe(tiny, "child", dest, with_requires=True)
    assert [r.recipe_id for r in results] == ["base", "child"]
    assert (dest / "shared.py").read_text(encoding="utf-8") == "child\n"  # replaced, since this run wrote it
    assert (dest / "extra" / "x.py").exists() and (dest / "app.py").exists()
    assert results[-1].requires == ("base",) and results[-1].uses == ("loose",)


def test_placeholders_are_collected(tiny: Kitchen):
    assert commands.placeholders(tiny, "base") == ("app_name",)
    assert commands.placeholders(tiny, "child") == ()


def test_check_reports_every_rule(tiny: Kitchen, tmp_path: Path):
    bad = Catalog.model_validate(
        {
            "recipes": [
                {"id": "base", "category": "backend", "description": "x", "tags": ["a"], "path": "recipes/backend/base", "requires": ["ghost", "base"]},
                {"id": "base", "category": "backend", "description": "x", "tags": [], "path": "recipes/backend/wrong"},
                {"id": "a", "category": "backend", "description": "x", "tags": ["a"], "path": "recipes/backend/a", "requires": ["b"]},
                {"id": "b", "category": "backend", "description": "x", "tags": ["a"], "path": "recipes/backend/b", "requires": ["a"]},
            ]
        }
    )
    messages = [str(p) for p in commands.check(Kitchen(root=tmp_path, catalog=bad))]
    assert any("requires unknown recipe 'ghost'" in m for m in messages)
    assert any("requires itself" in m for m in messages)
    assert any("duplicate id" in m for m in messages)
    assert any("expected 'recipes/backend/base'" in m for m in messages)
    assert any("no tags" in m for m in messages)
    assert any("requires cycle" in m for m in messages)
    assert any("recipes/backend/child exists on disk but is not in catalog.yaml" in m for m in messages)
    assert any("a: RECIPE.md missing" in m for m in messages)


def test_catalog_rejects_bad_ids_and_multiline_descriptions():
    with pytest.raises(ValueError, match="kebab-case"):
        Catalog.model_validate({"recipes": [{"id": "Bad_Id", "category": "x", "description": "d", "path": "p"}]})
    with pytest.raises(ValueError, match="one line"):
        Catalog.model_validate({"recipes": [{"id": "ok", "category": "x", "description": "a\nb", "path": "p"}]})


# --- the command line ---------------------------------------------------------------------------


def test_main_list_show_get_and_check(tiny: Kitchen, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    root = ["--root", str(tiny.root)]
    assert main([*root, "list", "--tag", "api"]) == 0
    out = capsys.readouterr().out
    assert "base " in out and "child" in out and "[requiere base]" in out and "loose" not in out

    assert main([*root, "list", "--json"]) == 0
    assert [r["id"] for r in json.loads(capsys.readouterr().out)] == ["base", "child", "loose"]

    assert main([*root, "show", "child"]) == 0
    assert capsys.readouterr().out.startswith("# child")
    assert main([*root, "show", "child", "--files"]) == 0
    assert capsys.readouterr().out.split() == ["extra/x.py", "shared.py"]

    dest = tmp_path / "out"
    assert main([*root, "get", "child", "--to", str(dest), "--with-requires"]) == 0
    out = capsys.readouterr().out
    assert "base: 2 archivos copiados" in out and "child: 2 archivos copiados" in out
    assert "se integra con: loose" in out and "sustituye los marcadores: {{app_name}}" in out

    assert main([*root, "get", "child", "--to", str(dest)]) == 0
    out = capsys.readouterr().out
    assert "ya existía, no se toca: shared.py" in out and "requiere: base" in out

    assert main([*root, "check"]) == 0
    assert capsys.readouterr().out.strip().endswith("3 recetas, 0 problemas")

    assert main([*root, "show", "nope"]) == 2
    assert "receta desconocida 'nope'" in capsys.readouterr().err


def test_main_without_a_kitchen_fails_clearly(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    assert main(["--root", str(tmp_path), "list"]) == 2
    assert "catalog.yaml" in capsys.readouterr().err
