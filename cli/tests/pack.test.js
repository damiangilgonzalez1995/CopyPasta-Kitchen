// The published package, not the checkout: pack it for real, unpack it somewhere else and ask THAT copy.
// npm drops some files on its own (`.gitignore`, and whatever a nested `.gitignore` names), so "the tests
// pass in the checkout" says nothing about what a user receives.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, readdirSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const shell = process.platform === 'win32';

test('the packed package serves every tracked recipe file, byte for byte', () => {
  const work = mkdtempSync(join(tmpdir(), 'copypasta-pack-'));
  execFileSync('npm', ['pack', '--pack-destination', work], { cwd: REPO, encoding: 'utf8', shell, stdio: ['ignore', 'pipe', 'ignore'] });
  assert.ok(!existsSync(join(REPO, 'unpacked-files.json')), 'postpack removes the side file from the checkout');

  const tarball = readdirSync(work).find((name) => name.endsWith('.tgz'));
  assert.ok(tarball, 'npm pack produced a tarball');
  // Relative name + cwd: bsdtar on Windows reads `C:` in an absolute path as a remote host.
  execFileSync('tar', ['-xzf', tarball], { cwd: work });
  const installed = join(work, 'package');
  // The package has one dependency; point at the checkout's copy instead of installing from the network.
  symlinkSync(join(REPO, 'node_modules'), join(installed, 'node_modules'), 'junction');

  const cli = join(installed, 'cli', 'copypasta.js');
  const copypasta = (...args) => execFileSync(process.execPath, [cli, ...args], { cwd: work, encoding: 'utf8' });

  assert.match(copypasta('check'), /\d+ recetas, 0 problemas/);

  const tracked = execFileSync('git', ['ls-files', '-z', 'recipes'], { cwd: REPO, encoding: 'utf8' }).split('\0').filter(Boolean);
  const recipes = JSON.parse(copypasta('list', '--json'));
  assert.ok(recipes.length >= 18);
  let compared = 0;
  for (const recipe of recipes) {
    const prefix = `recipes/${recipe.category}/${recipe.id}/files/`;
    const expected = tracked.filter((path) => path.startsWith(prefix)).map((path) => path.slice(prefix.length)).sort();
    const listed = copypasta('show', recipe.id, '--files').split('\n').filter(Boolean);
    assert.deepEqual(listed, expected, `${recipe.id}: the package lists other files than the repo tracks`);

    const dest = join(work, 'out', recipe.id);
    copypasta('get', recipe.id, '--to', dest);
    for (const relative of expected) {
      assert.ok(readFileSync(join(dest, relative)).equals(readFileSync(join(REPO, prefix, relative))), `${recipe.id}: ${relative} differs`);
      compared += 1;
    }
  }
  assert.ok(compared > 200, `only ${compared} files compared`);
});
