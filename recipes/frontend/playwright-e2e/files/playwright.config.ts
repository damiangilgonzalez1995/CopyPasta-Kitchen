/**
 * E2E against the app in fake mode: no backend, no Supabase, no network. Playwright builds the app with
 * `--mode fake` (VITE_API_MODE=fake, VITE_AUTH_PROVIDER=fake) and serves it with `vite preview`.
 * The port is derived from the checkout path, so two worktrees can run at once.
 */

import { createHash } from 'node:crypto'

import { defineConfig, devices } from '@playwright/test'

const port = Number(process.env.E2E_PORT ?? 40000 + (parseInt(createHash('sha1').update(process.cwd()).digest('hex').slice(0, 8), 16) % 10000))
const ci = Boolean(process.env.CI)

export default defineConfig({
  testDir: 'e2e',
  outputDir: 'e2e/.results',
  timeout: 30_000,
  retries: ci ? 2 : 0,
  reporter: ci ? [['list'], ['html', { open: 'never', outputFolder: 'e2e/.report' }]] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `vite build --mode fake --outDir dist-fake --emptyOutDir && vite preview --outDir dist-fake --host 127.0.0.1 --port ${port} --strictPort`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'phone', use: { ...devices['Pixel 7'] } },
  ],
})
