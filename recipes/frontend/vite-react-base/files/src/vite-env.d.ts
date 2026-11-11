/// <reference types="vite/client" />

// Every VITE_* var used by the app is declared here (and documented in .env.example).
interface ImportMetaEnv {
  readonly VITE_API_MODE: 'http' | 'fake'
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
