// The catalog: `catalog.yaml` validated into plain frozen objects, plus where the recipes live on disk.
//
// Two layouts are supported, same code:
// - the repo checkout (`catalog.yaml` and `recipes/` at the root, two levels above this file);
// - the installed npm package, which carries both at its root, in the same place.
import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { parse as parseYaml } from 'yaml';

const ID_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const RECIPE_KEYS = ['id', 'category', 'description', 'tags', 'path', 'requires', 'uses'];
const PACKAGE_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

export class CatalogError extends Error {}

export class UnknownRecipeError extends Error {
  constructor(recipeId) {
    super(`unknown recipe '${recipeId}'`);
    this.recipeId = recipeId;
  }
}

function text(entry, key, where) {
  const value = entry[key];
  if (typeof value !== 'string' || value.trim() === '') throw new CatalogError(`${where}: '${key}' is required and must be text`);
  return value;
}

function idList(entry, key, where) {
  const value = entry[key] ?? [];
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) {
    throw new CatalogError(`${where}: '${key}' must be a list of text`);
  }
  return Object.freeze([...value]);
}

function parseRecipe(entry, index) {
  if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) throw new CatalogError(`recipes[${index}]: must be a mapping`);
  const where = typeof entry.id === 'string' ? entry.id : `recipes[${index}]`;
  for (const key of Object.keys(entry)) {
    if (!RECIPE_KEYS.includes(key)) throw new CatalogError(`${where}: unknown key '${key}'`);
  }
  const id = text(entry, 'id', where);
  if (!ID_PATTERN.test(id)) throw new CatalogError(`id must be kebab-case: '${id}'`);
  const description = text(entry, 'description', where).trim();
  if (description.includes('\n')) throw new CatalogError(`${where}: description must be one line`);
  return Object.freeze({
    id,
    category: text(entry, 'category', where),
    description,
    tags: idList(entry, 'tags', where),
    path: text(entry, 'path', where),
    requires: idList(entry, 'requires', where),
    uses: idList(entry, 'uses', where),
  });
}

/** Validates the parsed YAML. Unknown keys are an error: a typo in `requires` must not pass silently. */
export function parseCatalog(data) {
  const source = data ?? {};
  if (typeof source !== 'object' || Array.isArray(source)) throw new CatalogError('catalog.yaml must be a mapping with a `recipes` list');
  for (const key of Object.keys(source)) {
    if (key !== 'recipes') throw new CatalogError(`catalog.yaml: unknown key '${key}'`);
  }
  const entries = source.recipes ?? [];
  if (!Array.isArray(entries)) throw new CatalogError('catalog.yaml: `recipes` must be a list');
  return Object.freeze({ recipes: Object.freeze(entries.map(parseRecipe)) });
}

export function getRecipeEntry(catalog, recipeId) {
  const recipe = catalog.recipes.find((candidate) => candidate.id === recipeId);
  if (!recipe) throw new UnknownRecipeError(recipeId);
  return recipe;
}

export function filterRecipes(catalog, { tag, category } = {}) {
  return catalog.recipes.filter(
    (recipe) => (tag === undefined || recipe.tags.includes(tag)) && (category === undefined || recipe.category === category),
  );
}

/** The recipe and everything it `requires`, transitively, dependencies first. */
export function closure(catalog, recipeId) {
  const ordered = [];
  const visit = (current, trail) => {
    if (trail.includes(current)) throw new CatalogError(`requires cycle: ${[...trail, current].join(' -> ')}`);
    const recipe = getRecipeEntry(catalog, current);
    for (const dependency of recipe.requires) visit(dependency, [...trail, current]);
    if (!ordered.includes(recipe)) ordered.push(recipe);
  };
  visit(recipeId, []);
  return ordered;
}

export const recipeDir = (kitchen, recipe) => join(kitchen.root, recipe.path);
export const recipeMd = (kitchen, recipe) => join(recipeDir(kitchen, recipe), 'RECIPE.md');
export const filesDir = (kitchen, recipe) => join(recipeDir(kitchen, recipe), 'files');

const isFile = (path) => existsSync(path) && statSync(path).isFile();
const isDir = (path) => existsSync(path) && statSync(path).isDirectory();
const holdsKitchen = (folder) => isFile(join(folder, 'catalog.yaml')) && isDir(join(folder, 'recipes'));

/** The package first (it carries its own copy), then `start` upwards. */
export function findRoot(start, { packageRoot = PACKAGE_ROOT } = {}) {
  const candidates = [resolve(packageRoot)];
  if (start !== undefined) {
    let current = resolve(start);
    for (;;) {
      candidates.push(current);
      const parent = dirname(current);
      if (parent === current) break;
      current = parent;
    }
  }
  const found = candidates.find(holdsKitchen);
  if (!found) throw new CatalogError('catalog.yaml not found: run inside the CopyPasta-Kitchen checkout or install the package');
  return found;
}

export function loadCatalog(path) {
  if (!isFile(path)) throw new CatalogError(`catalog.yaml not found at ${path}`);
  return parseCatalog(parseYaml(readFileSync(path, 'utf8')));
}

/** A catalog bound to the directory that holds `catalog.yaml` and `recipes/`. */
export function openKitchen(root) {
  const resolved = root === undefined ? findRoot(process.cwd()) : resolve(root);
  return Object.freeze({ root: resolved, catalog: loadCatalog(join(resolved, 'catalog.yaml')) });
}
