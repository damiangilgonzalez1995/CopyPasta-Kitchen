// What each command does, without printing: `main.js` only formats. Tested directly.
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

import { CatalogError, UnknownRecipeError, closure, filesDir, filterRecipes, getRecipeEntry, recipeMd } from './catalog.js';

// npm never packs a `.gitignore` (nor `.npmrc`), wherever it sits. A recipe that ships one would lose it
// in the published package, so `scripts/prepack.js` writes those files into this side file, keyed by their
// path from the kitchen root, and every read of a recipe file goes through here. In a checkout the side
// file does not exist and the real files are on disk.
const UNPACKED_FILE = 'unpacked-files.json';

function unpacked(kitchen) {
  const path = join(kitchen.root, UNPACKED_FILE);
  return existsSync(path) ? JSON.parse(readFileSync(path, 'utf8')) : {};
}

function walk(folder, prefix = '') {
  if (!existsSync(folder) || !statSync(folder).isDirectory()) return [];
  const found = [];
  for (const entry of readdirSync(folder, { withFileTypes: true })) {
    const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) found.push(...walk(join(folder, entry.name), relative));
    else if (entry.isFile()) found.push(relative);
  }
  return found;
}

const byCodePoint = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

export function listRecipes(kitchen, filters = {}) {
  return filterRecipes(kitchen.catalog, filters);
}

export function showRecipe(kitchen, recipeId) {
  return readFileSync(recipeMd(kitchen, getRecipeEntry(kitchen.catalog, recipeId)), 'utf8');
}

/** Relative paths of `files/`, sorted, with `/` separators. */
export function recipeFiles(kitchen, recipeId) {
  const recipe = getRecipeEntry(kitchen.catalog, recipeId);
  const prefix = `${recipe.path}/files/`;
  const fromSideFile = Object.keys(unpacked(kitchen))
    .filter((path) => path.startsWith(prefix))
    .map((path) => path.slice(prefix.length));
  return [...new Set([...walk(filesDir(kitchen, recipe)), ...fromSideFile])].sort(byCodePoint);
}

/** The bytes of one recipe file, from disk or from the side file of the published package. */
function readRecipeFile(kitchen, recipe, relative) {
  const onDisk = join(filesDir(kitchen, recipe), relative);
  if (existsSync(onDisk)) return readFileSync(onDisk);
  const encoded = unpacked(kitchen)[`${recipe.path}/files/${relative}`];
  if (encoded === undefined) throw new CatalogError(`${recipe.id}: ${relative} is listed but cannot be read`);
  return Buffer.from(encoded, 'base64');
}

/**
 * Copies `files/` of the recipe (and of what it `requires`, if asked) into `destination`.
 *
 * Existing files are never overwritten unless `force`: a template must not clobber the project's own code.
 * The exception is a file this same run just copied from a required recipe: a recipe that `requires` another
 * may replace its files (react-app-router replaces App.tsx of vite-react-base).
 */
export function getRecipe(kitchen, recipeId, destination, { force = false, withRequires = false } = {}) {
  const recipes = withRequires ? closure(kitchen.catalog, recipeId) : [getRecipeEntry(kitchen.catalog, recipeId)];
  const writtenNow = new Set();
  return recipes.map((recipe) => {
    const copied = [];
    const skipped = [];
    for (const relative of recipeFiles(kitchen, recipe.id)) {
      const target = resolve(destination, relative);
      if (existsSync(target) && !force && !writtenNow.has(target)) {
        skipped.push(relative);
        continue;
      }
      writtenNow.add(target);
      mkdirSync(dirname(target), { recursive: true });
      const source = join(filesDir(kitchen, recipe), relative);
      if (existsSync(source)) copyFileSync(source, target);
      else writeFileSync(target, readRecipeFile(kitchen, recipe, relative));
      copied.push(relative);
    }
    return Object.freeze({ recipeId: recipe.id, copied, skipped, requires: recipe.requires, uses: recipe.uses });
  });
}

/** `{{name}}` markers found in the recipe files: what the consumer has to replace after copying. */
export function placeholders(kitchen, recipeId) {
  const recipe = getRecipeEntry(kitchen.catalog, recipeId);
  const found = new Set();
  for (const relative of recipeFiles(kitchen, recipeId)) {
    const bytes = readRecipeFile(kitchen, recipe, relative);
    if (bytes.includes(0)) continue; // binary file (an image, a font)
    for (const match of bytes.toString('utf8').matchAll(/\{\{([a-z_][a-z0-9_]*)\}\}/g)) found.add(match[1]);
  }
  return [...found].sort(byCodePoint);
}

class Problem {
  constructor(recipeId, message) {
    this.recipeId = recipeId;
    this.message = message;
  }

  toString() {
    return `${this.recipeId ?? 'catalog'}: ${this.message}`;
  }
}

/**
 * The rules of AGENTS.md: every recipe on disk is in the catalog, every entry exists with RECIPE.md and files/,
 * ids are unique, `requires`/`uses` point to real recipes, no self-reference, no `requires` cycle.
 */
export function check(kitchen) {
  const problems = [];
  const { catalog } = kitchen;
  const ids = new Set(catalog.recipes.map((recipe) => recipe.id));

  const seen = new Set();
  for (const recipe of catalog.recipes) {
    const report = (message) => problems.push(new Problem(recipe.id, message));
    if (seen.has(recipe.id)) report('duplicate id');
    seen.add(recipe.id);

    const expected = `recipes/${recipe.category}/${recipe.id}`;
    if (recipe.path !== expected) report(`path is '${recipe.path}', expected '${expected}'`);
    const readme = recipeMd(kitchen, recipe);
    if (!existsSync(readme)) report('RECIPE.md missing');
    else if (!readFileSync(readme, 'utf8').trimStart().startsWith(`# ${recipe.id}`)) report(`RECIPE.md must start with '# ${recipe.id}'`);
    if (recipeFiles(kitchen, recipe.id).length === 0) report('files/ missing or empty');
    if (recipe.tags.length === 0) report('no tags');
    for (const field of ['requires', 'uses']) {
      for (const other of recipe[field]) {
        if (other === recipe.id) report(`${field} itself`);
        else if (!ids.has(other)) report(`${field} unknown recipe '${other}'`);
      }
    }
    try {
      closure(catalog, recipe.id);
    } catch (error) {
      if (!(error instanceof CatalogError || error instanceof UnknownRecipeError)) throw error;
      report(error.message);
    }
  }

  const recipesDir = join(kitchen.root, 'recipes');
  const inCatalog = new Set(catalog.recipes.map((recipe) => recipe.path));
  const onDisk = [];
  if (existsSync(recipesDir)) {
    for (const category of readdirSync(recipesDir, { withFileTypes: true })) {
      if (!category.isDirectory()) continue;
      for (const folder of readdirSync(join(recipesDir, category.name), { withFileTypes: true })) {
        if (folder.isDirectory() && !folder.name.startsWith('.')) onDisk.push(`recipes/${category.name}/${folder.name}`);
      }
    }
  }
  for (const path of onDisk.sort(byCodePoint)) {
    if (!inCatalog.has(path)) problems.push(new Problem(null, `${path} exists on disk but is not in catalog.yaml`));
  }
  return problems;
}
