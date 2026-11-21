// Public surface of the package: the CLI as a function, and the pieces behind it for a host program.
export { main, usage, USAGE } from './main.js';
export { CatalogError, UnknownRecipeError, findRoot, openKitchen, parseCatalog } from './catalog.js';
export { check, getRecipe, listRecipes, placeholders, recipeFiles, showRecipe } from './commands.js';
