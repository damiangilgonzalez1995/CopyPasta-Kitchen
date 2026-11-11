/**
 * Factory: builds the `Api` the settings name (VITE_API_MODE). Switching backend = changing a variable.
 * The fake is a dynamic import: Vite emits it as a separate chunk that is only downloaded in `fake` mode.
 */

import type { TokenProvider } from '../auth/token-provider'
import type { ApiMode } from '../config'
import type { Api } from './api'
import { createHttpApi } from './http-api'
import { createHttpClient } from './http-client'

export type MakeApiOptions = {
  mode: ApiMode
  apiUrl: string
  tokens?: TokenProvider
  onSessionExpired?: () => void
}

export async function makeApi(options: MakeApiOptions): Promise<Api> {
  switch (options.mode) {
    case 'http':
      return createHttpApi(
        createHttpClient({ baseUrl: options.apiUrl, tokens: options.tokens, onSessionExpired: options.onSessionExpired }),
      )
    case 'fake': {
      const { createFakeApi } = await import('./fake/fake-api')
      return createFakeApi()
    }
  }
}
