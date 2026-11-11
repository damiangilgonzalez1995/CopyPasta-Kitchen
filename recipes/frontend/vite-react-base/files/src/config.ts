/**
 * Frontend settings: the ONLY place that reads `import.meta.env`.
 * Values come from `.env*` files at build time (Vite inlines them), so they are public: no secrets.
 */

export type ApiMode = 'http' | 'fake'

function apiMode(value: string | undefined): ApiMode {
  if (value === 'http' || value === 'fake') return value
  // No silent default: a typo in VITE_API_MODE must not ship a fake API to production.
  throw new Error(`VITE_API_MODE must be "http" or "fake", got ${JSON.stringify(value)}`)
}

export const CONFIG = {
  appName: '{{app_name}}',
  apiMode: apiMode(import.meta.env.VITE_API_MODE),
  apiUrl: import.meta.env.VITE_API_URL ?? '/api',
} as const
