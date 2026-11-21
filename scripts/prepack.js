// npm never packs a `.gitignore` or an `.npmrc`, wherever they sit, and a nested `.gitignore` also works
// as an ignore file for its folder. A recipe that ships one (vite-react-base does) would arrive incomplete.
//
// Before packing, this writes every tracked recipe file that `npm pack` is about to leave out into
// `unpacked-files.json` (path from the repo root -> base64). `cli/lib/commands.js` reads recipe files
// through that side file, so the published package serves exactly what the checkout serves.
// `--clean` removes the side file again (postpack): it must never exist in a checkout.
import { execFileSync } from 'node:child_process';
import { readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SIDE_FILE = join(ROOT, 'unpacked-files.json');

if (process.argv.includes('--clean')) {
  rmSync(SIDE_FILE, { force: true });
} else {
  rmSync(SIDE_FILE, { force: true });
  const run = (command, args) => execFileSync(command, args, { cwd: ROOT, encoding: 'utf8', shell: process.platform === 'win32' });
  const tracked = run('git', ['ls-files', '-z', 'recipes']).split('\0').filter(Boolean);
  // `--ignore-scripts` keeps this from calling itself; the dry run lists what would be packed.
  const packed = new Set(JSON.parse(run('npm', ['pack', '--dry-run', '--json', '--ignore-scripts']))[0].files.map((file) => file.path));
  const missing = tracked.filter((path) => !packed.has(path) && !path.endsWith('/.gitkeep'));
  const side = Object.fromEntries(missing.map((path) => [path, readFileSync(join(ROOT, path)).toString('base64')]));
  writeFileSync(SIDE_FILE, `${JSON.stringify(side, null, 2)}\n`);
  process.stderr.write(`prepack: ${missing.length} recipe file(s) npm would drop, carried in unpacked-files.json\n`);
  for (const path of missing) process.stderr.write(`  ${path}\n`);
}
