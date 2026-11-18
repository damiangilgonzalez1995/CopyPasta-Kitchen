/**
 * Auth contract of the app: who is signed in and where the bearer token comes from.
 * Two implementations, same type: `createSupabaseAuth` (supabase-js) and `createFakeAuth` (in memory, persisted
 * in localStorage so a reload keeps you in). `makeAuth` picks one from the settings (VITE_AUTH_PROVIDER).
 *
 * Screens never import supabase-js: they use `useSession()` (session-context.tsx), and the HTTP client only
 * sees a `TokenProvider` (`tokenProviderOf(auth)`).
 */

import type { TokenProvider } from './token-provider'

export type AuthUser = {
  id: string
  email: string
}

export type Session = {
  accessToken: string
  user: AuthUser
}

export type Credentials = {
  email: string
  password: string
}

/** Stable codes: the login screen shows a message per code, never the provider's text. */
export type AuthErrorCode = 'invalid_credentials' | 'email_not_confirmed' | 'rate_limited' | 'unavailable'

export class AuthError extends Error {
  constructor(
    readonly code: AuthErrorCode,
    readonly cause?: unknown,
  ) {
    super(`Auth error: ${code}`)
    this.name = 'AuthError'
  }
}

export type Auth = {
  /** The stored session, or null when signed out. Never throws: a broken store is "signed out". */
  getSession(): Promise<Session | null>
  /** Email + password. Throws `AuthError`. */
  signIn(credentials: Credentials): Promise<Session>
  /** Clears the local session first; telling the provider is best effort. Never throws. */
  signOut(): Promise<void>
  /** New access token with the refresh token. Null = the session is over. Never throws. */
  refresh(): Promise<Session | null>
  /** Fires with the new session on sign in, refresh and sign out. Returns the unsubscribe. */
  onChange(listener: (session: Session | null) => void): () => void
}

/** What the HTTP client needs, taken from the auth. */
export function tokenProviderOf(auth: Auth): TokenProvider {
  return {
    getToken: async () => (await auth.getSession())?.accessToken ?? null,
    refresh: async () => (await auth.refresh())?.accessToken ?? null,
  }
}
