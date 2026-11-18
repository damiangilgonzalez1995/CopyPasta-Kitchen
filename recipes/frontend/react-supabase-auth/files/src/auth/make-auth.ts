/**
 * Factory: builds the `Auth` the settings name (VITE_AUTH_PROVIDER). Both implementations are dynamic
 * imports: supabase-js is a separate chunk the fake build never downloads, and vice versa.
 */

import type { Auth } from './auth'
import type { AuthSettings } from './settings'

export async function makeAuth(settings: AuthSettings): Promise<Auth> {
  switch (settings.provider) {
    case 'supabase': {
      const { createSupabaseAuth } = await import('./supabase-auth')
      return createSupabaseAuth({ url: settings.supabaseUrl!, anonKey: settings.supabaseAnonKey! })
    }
    case 'fake': {
      const { createFakeAuth } = await import('./fake-auth')
      return createFakeAuth()
    }
  }
}
