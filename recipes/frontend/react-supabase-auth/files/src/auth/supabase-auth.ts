/**
 * `Auth` on supabase-js. The client persists the session in localStorage (`sb-<ref>-auth-token`) and
 * refreshes the token on its own before it expires; `refresh()` is the explicit path the HTTP client takes
 * after a 401. Loaded with a dynamic import by `makeAuth`, so the fake build never ships supabase-js.
 *
 * `fetcher` is the test seam: the tests run the real supabase-js against a fake GoTrue (see fake-gotrue.ts).
 */

import { createClient, isAuthApiError, type Session as SupabaseSession, type SupabaseClient } from '@supabase/supabase-js'

import { AuthError, type Auth, type AuthErrorCode, type Session } from './auth'

export type SupabaseAuthOptions = {
  url: string
  anonKey: string
  fetcher?: typeof fetch
  storage?: Storage
}

export function createSupabaseAuth(options: SupabaseAuthOptions): Auth {
  const client: SupabaseClient = createClient(options.url, options.anonKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: false, // no OAuth/magic-link callback in this recipe
      ...(options.storage ? { storage: options.storage } : {}),
    },
    ...(options.fetcher ? { global: { fetch: options.fetcher } } : {}),
  })

  return {
    async getSession() {
      try {
        return toSession((await client.auth.getSession()).data.session)
      } catch {
        return null
      }
    },

    async signIn({ email, password }) {
      const { data, error } = await client.auth.signInWithPassword({ email: email.trim(), password })
      if (error) throw new AuthError(codeOf(error), error)
      const session = toSession(data.session)
      if (!session) throw new AuthError('unavailable')
      return session
    },

    async signOut() {
      // Clears localStorage at once; the request to GoTrue is a courtesy (the token expires anyway).
      await client.auth.signOut({ scope: 'local' }).catch(() => undefined)
    },

    async refresh() {
      try {
        const { data, error } = await client.auth.refreshSession()
        if (error) {
          // A rejected refresh token = the session is over. A network failure is not: keep the session.
          if (isAuthApiError(error)) await client.auth.signOut({ scope: 'local' }).catch(() => undefined)
          return null
        }
        return toSession(data.session)
      } catch {
        return null
      }
    },

    onChange(listener) {
      const { data } = client.auth.onAuthStateChange((_event, session) => listener(toSession(session)))
      return () => data.subscription.unsubscribe()
    },
  }
}

function toSession(session: SupabaseSession | null): Session | null {
  if (!session?.access_token) return null
  return { accessToken: session.access_token, user: { id: session.user.id, email: session.user.email ?? '' } }
}

/** Only the code leaves this module: supabase's message is kept as `cause`, not shown. */
function codeOf(error: { status?: number; code?: string }): AuthErrorCode {
  if (error.code === 'email_not_confirmed') return 'email_not_confirmed'
  if (error.status === 429) return 'rate_limited'
  if (error.code === 'invalid_credentials' || error.status === 400 || error.status === 401) return 'invalid_credentials'
  return 'unavailable'
}
