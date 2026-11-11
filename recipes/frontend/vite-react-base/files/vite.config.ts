import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Dev/preview proxy: the browser calls /api on the same origin, Vite forwards it to the Python backend.
// No CORS in dev, and SSE streams pass through untouched.
const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'
const proxy = { '/api': { target: backend, changeOrigin: true } }

export default defineConfig({
  plugins: [react()],
  server: { proxy },
  preview: { proxy },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['src/test-setup.ts'],
  },
})
