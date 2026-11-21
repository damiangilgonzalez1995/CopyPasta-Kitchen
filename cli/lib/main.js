// `copypasta`: list, show, get and check recipes. Output is made for an agent's context: short, no decoration.
import { parseArgs } from 'node:util';

import { CatalogError, UnknownRecipeError, openKitchen } from './catalog.js';
import * as commands from './commands.js';

/** The help text, under the name the user typed: a host CLI (`harness recipes`) passes its own. */
export const usage = (name = 'copypasta') => `${name}: recetas de CopyPasta-Kitchen (descubrir, leer y copiar)

    ${name} list [--tag T] [--category C] [--json]            ids y descripción de una línea
    ${name} show <id> [--files]                               el RECIPE.md de una receta, o sus archivos
    ${name} get <id> --to DIR [--with-requires] [--force]     copia files/ de la receta al proyecto
    ${name} check                                             valida catalog.yaml contra recipes/

    --root DIR    carpeta con catalog.yaml y recipes/ (por defecto: el paquete o el checkout)
`;
export const USAGE = usage();

class UsageError extends Error {}

const OPTIONS = {
  list: { tag: { type: 'string' }, category: { type: 'string' }, json: { type: 'boolean' } },
  show: { files: { type: 'boolean' } },
  get: { to: { type: 'string' }, 'with-requires': { type: 'boolean' }, force: { type: 'boolean' } },
  check: {},
};
const TAKES_ID = ['show', 'get'];

function parse(argv) {
  // `--root` is accepted before or after the command, so it is lifted out first.
  const rest = [];
  let root;
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--root') {
      root = argv[index + 1];
      if (root === undefined) throw new UsageError('--root necesita una carpeta');
      index += 1;
    } else if (arg.startsWith('--root=')) root = arg.slice('--root='.length);
    else rest.push(arg);
  }
  const [command, ...tail] = rest;
  if (command === undefined) throw new UsageError('falta el comando');
  if (!(command in OPTIONS)) throw new UsageError(`comando desconocido '${command}'`);
  let parsed;
  try {
    parsed = parseArgs({ args: tail, options: OPTIONS[command], allowPositionals: true, strict: true });
  } catch (error) {
    throw new UsageError(error.message);
  }
  const expected = TAKES_ID.includes(command) ? 1 : 0;
  if (parsed.positionals.length !== expected) {
    throw new UsageError(expected ? `'${command}' necesita exactamente un id de receta` : `'${command}' no lleva argumentos`);
  }
  if (command === 'get' && !parsed.values.to) throw new UsageError("'get' necesita --to DIR");
  return { root, command, id: parsed.positionals[0], options: parsed.values };
}

const DEFAULT_IO = {
  out: (text) => process.stdout.write(text),
  err: (text) => process.stderr.write(text),
};

/**
 * Runs the CLI and returns the exit code. `io` is how tests (and a host CLI) capture the output;
 * `io.command` is the name printed in help and hints (`copypasta` unless a host says otherwise).
 */
export function main(argv = process.argv.slice(2), io = DEFAULT_IO) {
  const name = io.command ?? 'copypasta';
  const print = (line = '') => io.out(`${line}\n`);
  if (argv.includes('--help') || argv.includes('-h')) {
    io.out(usage(name));
    return 0;
  }
  try {
    const args = parse(argv);
    return run(openKitchen(args.root), args, print, io, name);
  } catch (error) {
    if (error instanceof UsageError) io.err(`error: ${error.message}\n\n${usage(name)}`);
    else if (error instanceof UnknownRecipeError) io.err(`error: receta desconocida '${error.recipeId}'. Prueba \`${name} list\`.\n`);
    else if (error instanceof CatalogError) io.err(`error: ${error.message}\n`);
    else throw error;
    return 2;
  }
}

function run(kitchen, { command, id, options }, print, io, name) {
  if (command === 'list') {
    const recipes = commands.listRecipes(kitchen, { tag: options.tag, category: options.category });
    if (options.json) {
      const rows = recipes.map(({ id: recipeId, category, description, tags, requires, uses }) => ({ id: recipeId, category, description, tags, requires, uses }));
      print(JSON.stringify(rows, null, 2));
      return 0;
    }
    const width = Math.max(0, ...recipes.map((recipe) => recipe.id.length));
    for (const recipe of recipes) {
      const extra = recipe.requires.length ? `  [requiere ${recipe.requires.join(', ')}]` : '';
      print(`${recipe.id.padEnd(width)}  ${recipe.category.padEnd(8)}  ${recipe.description}${extra}`);
    }
    return 0;
  }

  if (command === 'show') {
    if (options.files) print(commands.recipeFiles(kitchen, id).join('\n'));
    else io.out(commands.showRecipe(kitchen, id));
    return 0;
  }

  if (command === 'get') {
    const withRequires = Boolean(options['with-requires']);
    const results = commands.getRecipe(kitchen, id, options.to, { force: Boolean(options.force), withRequires });
    for (const result of results) {
      print(`${result.recipeId}: ${result.copied.length} archivos copiados en ${options.to}`);
      for (const path of result.skipped) print(`  ya existía, no se toca: ${path}  (usa --force para sobrescribir)`);
    }
    const last = results.at(-1);
    if (last.requires.length && !withRequires) print(`requiere: ${last.requires.join(', ')}  (cópialas también, o usa --with-requires)`);
    if (last.uses.length) print(`se integra con: ${last.uses.join(', ')}`);
    const markers = [...new Set(results.flatMap((result) => commands.placeholders(kitchen, result.recipeId)))].sort();
    if (markers.length) print(`sustituye los marcadores: ${markers.map((marker) => `{{${marker}}}`).join(', ')}`);
    print(`lee cómo adaptarla: ${name} show ${id}`);
    return 0;
  }

  // check
  const problems = commands.check(kitchen);
  for (const problem of problems) print(String(problem));
  print(`${kitchen.catalog.recipes.length} recetas, ${problems.length} problemas`);
  return problems.length ? 1 : 0;
}
