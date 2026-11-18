"""`copypasta`: list, show, get and check recipes. Output is made for an agent's context: short, no decoration.

    copypasta list [--tag T] [--category C] [--json]
    copypasta show <id> [--files]
    copypasta get <id> --to DIR [--with-requires] [--force]
    copypasta check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import commands
from .catalog import Kitchen, open_kitchen


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="copypasta", description="Recetas de CopyPasta-Kitchen: descubrir, leer y copiar.")
    parser.add_argument("--root", type=Path, help="carpeta con catalog.yaml y recipes/ (por defecto: el paquete o el checkout)")
    sub = parser.add_subparsers(dest="command", required=True)

    list_cmd = sub.add_parser("list", help="ids y descripción de una línea")
    list_cmd.add_argument("--tag")
    list_cmd.add_argument("--category")
    list_cmd.add_argument("--json", action="store_true", help="salida JSON (id, category, description, tags, requires, uses)")

    show_cmd = sub.add_parser("show", help="el RECIPE.md de una receta")
    show_cmd.add_argument("id")
    show_cmd.add_argument("--files", action="store_true", help="en vez del RECIPE.md, la lista de archivos de files/")

    get_cmd = sub.add_parser("get", help="copia files/ de la receta al proyecto")
    get_cmd.add_argument("id")
    get_cmd.add_argument("--to", type=Path, required=True, help="carpeta destino (se crea si no existe)")
    get_cmd.add_argument("--with-requires", action="store_true", help="copia también las recetas que requiere, primero")
    get_cmd.add_argument("--force", action="store_true", help="sobrescribe archivos que ya existan")

    sub.add_parser("check", help="valida catalog.yaml contra recipes/ (reglas de AGENTS.md)")
    return parser


def main(argv: list[str] | None = None) -> int:
    # Agents read us through a pipe; on Windows that defaults to the ANSI code page and breaks the accents.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        kitchen = open_kitchen(args.root)
    except FileNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    try:
        return run(kitchen, args)
    except KeyError as error:
        print(f"error: receta desconocida {error.args[0]!r}. Prueba `copypasta list`.", file=sys.stderr)
        return 2


def run(kitchen: Kitchen, args: argparse.Namespace) -> int:
    if args.command == "list":
        recipes = commands.list_recipes(kitchen, tag=args.tag, category=args.category)
        if args.json:
            print(json.dumps([recipe.model_dump(exclude={"path"}) for recipe in recipes], ensure_ascii=False, indent=2))
            return 0
        width = max((len(recipe.id) for recipe in recipes), default=0)
        for recipe in recipes:
            extra = ""
            if recipe.requires:
                extra += f"  [requiere {', '.join(recipe.requires)}]"
            print(f"{recipe.id:<{width}}  {recipe.category:<8}  {recipe.description}{extra}")
        return 0

    if args.command == "show":
        if args.files:
            print("\n".join(commands.recipe_files(kitchen, args.id)))
        else:
            print(commands.show_recipe(kitchen, args.id), end="")
        return 0

    if args.command == "get":
        results = commands.get_recipe(kitchen, args.id, args.to, force=args.force, with_requires=args.with_requires)
        for result in results:
            print(f"{result.recipe_id}: {len(result.copied)} archivos copiados en {args.to}")
            for path in result.skipped:
                print(f"  ya existía, no se toca: {path}  (usa --force para sobrescribir)")
        last = results[-1]
        if last.requires and not args.with_requires:
            print(f"requiere: {', '.join(last.requires)}  (cópialas también, o usa --with-requires)")
        if last.uses:
            print(f"se integra con: {', '.join(last.uses)}")
        markers = sorted({m for result in results for m in commands.placeholders(kitchen, result.recipe_id)})
        if markers:
            print(f"sustituye los marcadores: {', '.join('{{' + m + '}}' for m in markers)}")
        print(f"lee cómo adaptarla: copypasta show {args.id}")
        return 0

    if args.command == "check":
        problems = commands.check(kitchen)
        for problem in problems:
            print(problem)
        count = len(kitchen.catalog.recipes)
        print(f"{count} recetas, {len(problems)} problemas")
        return 1 if problems else 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
