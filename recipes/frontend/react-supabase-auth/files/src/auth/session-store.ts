/**
 * Session state of the app, outside React: `loading` -> `signed_in` | `signed_out` (+ `expired`).
 * `main.tsx` builds it once, gives `expire` to the HTTP client (`onSessionExpired`) and the store to
 * `<SessionProvider>`. Tested without rendering anything.
 */

import type { Auth, Credentials, Session } from './auth'

export type SessionStatus = 'loading' | 'signed_in' | 'signed_out'

export type SessionState = {
  status: SessionStatus
  session: Session | null
  /** True when the last session ended by itself (401 after refresh), so the login can say so. */
  expired: boolean
}

export function createSessionStore(auth: Auth) {
  let state: SessionState = { status: 'loading', session: null, expired: false }
  const listeners = new Set<() => void>()

  function set(next: Partial<SessionState>) {
    state = { ...state, ...next }
    listeners.forEach((listener) => listener())
  }

  function apply(session: Session | null) {
    set({ status: session ? 'signed_in' : 'signed_out', session })
  }

  return {
    getState: () => state,
    subscribe(listener: () => void) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },

    /** Reads the stored session and follows the provider from then on (refresh, sign out in another tab). */
    async start(): Promise<() => void> {
      const stop = auth.onChange(apply)
      apply(await auth.getSession())
      return stop
    },

    async signIn(credentials: Credentials): Promise<void> {
      const session = await auth.signIn(credentials) // throws AuthError; the screen shows it by code
      set({ status: 'signed_in', session, expired: false })
    },

    async signOut(): Promise<void> {
      await auth.signOut()
      set({ status: 'signed_out', session: null, expired: false })
    },

    /** A 401 survived the refresh: the session is over. Called by the HTTP client. */
    expire(): void {
      void auth.signOut()
      set({ status: 'signed_out', session: null, expired: true })
    },
  }
}

export type SessionStore = ReturnType<typeof createSessionStore>
