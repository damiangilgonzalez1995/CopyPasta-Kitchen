// The CLI against the real catalog (so a broken recipe fails here too) and against a tiny kitchen in tmp.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { CatalogError, findRoot, openKitchen, parseCatalog } from '../lib/catalog.js';
import * as commands from '../lib/commands.js';
import { main } from '../lib/main.js';

const REPO = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

const TINY_CATALOG = `
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
`;

function tmp() {
  return mkdtempSync(join(tmpdir(), 'copypasta-'));
}

/** base <- child (requires base, replaces one of its files); loose uses child. */
function tiny() {
  const root = tmp();
  writeFileSync(join(root, 'catalog.yaml'), TINY_CATALOG, 'utf8');
  const recipes = {
    'backend/base': { 'app.py': "name = '{{app_name}}'\n", 'shared.py': 'base\n' },
    'backend/child': { 'shared.py': 'child\n', 'extra/x.py': 'x\n' },
    'frontend/loose': { 'index.html': '<h1>{{app_name}}</h1>' },
  };
  for (const [recipe, files] of Object.entries(recipes)) {
    const folder = join(root, 'recipes', recipe);
    mkdirSync(join(folder, 'files'), { recursive: true });
    writeFileSync(join(folder, 'RECIPE.md'), `# ${recipe.split('/')[1]}\n\n## Cuándo usarla\n`, 'utf8');
    for (const [name, content] of Object.entries(files)) {
      const target = join(folder, 'files', name);
      mkdirSync(dirname(target), { recursive: true });
      writeFileSync(target, content, 'utf8');
    }
  }
  return openKitchen(root);
}

/** Runs `main` capturing what it prints. */
function run(argv) {
  const out = [];
  const err = [];
  const code = main(argv, { out: (text) => out.push(text), err: (text) => err.push(text) });
  return { code, out: out.join(''), err: err.join('') };
}

// --- the real catalog -------------------------------------------------------------------------

test('the real catalog passes check', () => {
  const real = openKitchen(REPO);
  assert.deepEqual(commands.check(real).map(String), []);
  assert.ok(real.catalog.recipes.length >= 18);
});

test('every real recipe shows and lists files', () => {
  const real = openKitchen(REPO);
  for (const recipe of real.catalog.recipes) {
    assert.ok(commands.showRecipe(real, recipe.id).startsWith(`# ${recipe.id}`), recipe.id);
    assert.ok(commands.recipeFiles(real, recipe.id).length > 0, recipe.id);
  }
});

test('find root from a subfolder', () => {
  const outside = tmp();
  const kitchen = tiny();
  const sub = join(kitchen.root, 'recipes', 'backend');
  // The package's own copy wins when it exists; a start folder is the fallback, walked upwards.
  assert.equal(findRoot(sub, { packageRoot: outside }), kitchen.root);
  assert.equal(findRoot(outside), REPO);
});

// --- commands on the tiny kitchen ---------------------------------------------------------------

test('list filters by tag and category', () => {
  const kitchen = tiny();
  assert.deepEqual(commands.listRecipes(kitchen).map((r) => r.id), ['base', 'child', 'loose']);
  assert.deepEqual(commands.listRecipes(kitchen, { tag: 'extra' }).map((r) => r.id), ['child']);
  assert.deepEqual(commands.listRecipes(kitchen, { category: 'frontend' }).map((r) => r.id), ['loose']);
});

test('get copies files and never overwrites the project', () => {
  const kitchen = tiny();
  const dest = join(tmp(), 'project');
  mkdirSync(dest);
  writeFileSync(join(dest, 'app.py'), 'mine\n', 'utf8');

  const [result] = commands.getRecipe(kitchen, 'base', dest);
  assert.deepEqual(result.copied, ['shared.py']);
  assert.deepEqual(result.skipped, ['app.py']);
  assert.equal(readFileSync(join(dest, 'app.py'), 'utf8'), 'mine\n');

  const [forced] = commands.getRecipe(kitchen, 'base', dest, { force: true });
  assert.deepEqual(forced.skipped, []);
  assert.ok(readFileSync(join(dest, 'app.py'), 'utf8').startsWith('name'));
});

test('get with requires copies dependencies first and lets the child replace them', () => {
  const kitchen = tiny();
  const dest = join(tmp(), 'project');
  const results = commands.getRecipe(kitchen, 'child', dest, { withRequires: true });
  assert.deepEqual(results.map((r) => r.recipeId), ['base', 'child']);
  assert.equal(readFileSync(join(dest, 'shared.py'), 'utf8'), 'child\n'); // replaced, since this run wrote it
  assert.ok(existsSync(join(dest, 'extra', 'x.py')) && existsSync(join(dest, 'app.py')));
  assert.deepEqual(results.at(-1).requires, ['base']);
  assert.deepEqual(results.at(-1).uses, ['loose']);
});

test('placeholders are collected', () => {
  const kitchen = tiny();
  assert.deepEqual(commands.placeholders(kitchen, 'base'), ['app_name']);
  assert.deepEqual(commands.placeholders(kitchen, 'child'), []);
});

test('check reports every rule', () => {
  const kitchen = tiny();
  const bad = parseCatalog({
    recipes: [
      { id: 'base', category: 'backend', description: 'x', tags: ['a'], path: 'recipes/backend/base', requires: ['ghost', 'base'] },
      { id: 'base', category: 'backend', description: 'x', tags: [], path: 'recipes/backend/wrong' },
      { id: 'a', category: 'backend', description: 'x', tags: ['a'], path: 'recipes/backend/a', requires: ['b'] },
      { id: 'b', category: 'backend', description: 'x', tags: ['a'], path: 'recipes/backend/b', requires: ['a'] },
    ],
  });
  const messages = commands.check({ ...kitchen, catalog: bad }).map(String);
  const has = (text) => assert.ok(messages.some((m) => m.includes(text)), `missing: ${text}\n${messages.join('\n')}`);
  has("requires unknown recipe 'ghost'");
  has('requires itself');
  has('duplicate id');
  has("expected 'recipes/backend/base'");
  has('no tags');
  has('requires cycle');
  has('recipes/backend/child exists on disk but is not in catalog.yaml');
  has('a: RECIPE.md missing');
});

test('the catalog rejects bad ids, multiline descriptions and unknown keys', () => {
  const entry = { id: 'ok', category: 'x', description: 'd', path: 'p' };
  assert.throws(() => parseCatalog({ recipes: [{ ...entry, id: 'Bad_Id' }] }), /kebab-case/);
  assert.throws(() => parseCatalog({ recipes: [{ ...entry, description: 'a\nb' }] }), /one line/);
  assert.throws(() => parseCatalog({ recipes: [{ ...entry, requiers: ['x'] }] }), /unknown key 'requiers'/);
  assert.throws(() => parseCatalog({ recipes: [{ id: 'ok' }] }), CatalogError);
});

// --- the command line -----------------------------------------------------------------------------

test('main: list, show, get and check', () => {
  const kitchen = tiny();
  const root = ['--root', kitchen.root];

  let result = run([...root, 'list', '--tag', 'api']);
  assert.equal(result.code, 0);
  assert.ok(result.out.includes('base ') && result.out.includes('child') && result.out.includes('[requiere base]'));
  assert.ok(!result.out.includes('loose'));

  result = run([...root, 'list', '--json']);
  assert.equal(result.code, 0);
  const listed = JSON.parse(result.out);
  assert.deepEqual(listed.map((r) => r.id), ['base', 'child', 'loose']);
  assert.deepEqual(Object.keys(listed[0]), ['id', 'category', 'description', 'tags', 'requires', 'uses']);

  result = run([...root, 'show', 'child']);
  assert.equal(result.code, 0);
  assert.ok(result.out.startsWith('# child'));
  result = run([...root, 'show', 'child', '--files']);
  assert.deepEqual(result.out.split(/\s+/).filter(Boolean), ['extra/x.py', 'shared.py']);

  const dest = join(tmp(), 'out');
  result = run([...root, 'get', 'child', '--to', dest, '--with-requires']);
  assert.equal(result.code, 0);
  assert.ok(result.out.includes('base: 2 archivos copiados') && result.out.includes('child: 2 archivos copiados'));
  assert.ok(result.out.includes('se integra con: loose') && result.out.includes('sustituye los marcadores: {{app_name}}'));

  result = run([...root, 'get', 'child', '--to', dest]);
  assert.equal(result.code, 0);
  assert.ok(result.out.includes('ya existía, no se toca: shared.py') && result.out.includes('requiere: base'));

  result = run([...root, 'check']);
  assert.equal(result.code, 0);
  assert.ok(result.out.trim().endsWith('3 recetas, 0 problemas'));

  result = run([...root, 'show', 'nope']);
  assert.equal(result.code, 2);
  assert.ok(result.err.includes("receta desconocida 'nope'"));
});

test('main: without a kitchen it fails clearly', () => {
  const result = run(['--root', tmp(), 'list']);
  assert.equal(result.code, 2);
  assert.ok(result.err.includes('catalog.yaml'));
});

test('main: a bad command line explains itself instead of doing something else', () => {
  const kitchen = tiny();
  for (const argv of [[], ['frobnicate'], ['get', 'base'], ['show'], ['list', '--tag'], ['list', '--nope']]) {
    const result = run(['--root', kitchen.root, ...argv]);
    assert.equal(result.code, 2, `argv: ${argv.join(' ')}`);
    assert.ok(result.err.includes('copypasta'), `argv: ${argv.join(' ')}`);
  }
  const help = run(['--help']);
  assert.equal(help.code, 0);
  assert.ok(help.out.includes('copypasta get <id> --to DIR'));
});

test('main: a host CLI gets its own name in help and hints', () => {
  const kitchen = tiny();
  const out = [];
  const err = [];
  const io = { out: (text) => out.push(text), err: (text) => err.push(text), command: 'harness recipes' };
  assert.equal(main(['--help'], io), 0);
  assert.equal(main(['--root', kitchen.root, 'get', 'base', '--to', join(tmp(), 'x')], io), 0);
  assert.equal(main(['--root', kitchen.root, 'show', 'nope'], io), 2);
  assert.ok(out.join('').includes('harness recipes get <id> --to DIR'));
  assert.ok(out.join('').includes('lee cómo adaptarla: harness recipes show base'));
  assert.ok(err.join('').includes('`harness recipes list`'));
  assert.ok(!(out.join('') + err.join('')).includes('copypasta '), 'no hint points at a command the user did not type');
});
