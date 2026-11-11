/** Bootstrap: read settings -> build services with the factory -> render. The only place that wires things. */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from './App'
import { makeApi } from './api/make-api'
import { noAuth } from './auth/token-provider'
import { CONFIG } from './config'
import './styles/tokens.css'
import './styles/global.css'

async function start() {
  const api = await makeApi({
    mode: CONFIG.apiMode,
    apiUrl: CONFIG.apiUrl,
    tokens: noAuth, // replace with your TokenProvider (see auth/token-provider.ts)
    onSessionExpired: () => window.location.reload(),
  })
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App services={{ api }} />
    </StrictMode>,
  )
}

void start()
