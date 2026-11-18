/**
 * React binding of the session store: `useSession()` for screens and `<RequireSession>` as the guard.
 * The guard renders the login until there is a session; it does not depend on any router.
 */

import { createContext, useContext, useEffect, useSyncExternalStore, type ReactNode } from 'react'

import { LoginScreen } from './LoginScreen'
import type { SessionState, SessionStore } from './session-store'

const SessionContext = createContext<SessionStore | null>(null)

export function SessionProvider({ store, children }: { store: SessionStore; children: ReactNode }) {
  useEffect(() => {
    let stop: (() => void) | undefined
    void store.start().then((unsubscribe) => (stop = unsubscribe))
    return () => stop?.()
  }, [store])
  return <SessionContext.Provider value={store}>{children}</SessionContext.Provider>
}

export function useSession(): SessionState & Pick<SessionStore, 'signIn' | 'signOut'> {
  const store = useContext(SessionContext)
  if (!store) throw new Error('useSession() outside <SessionProvider>')
  const state = useSyncExternalStore(store.subscribe, store.getState)
  return { ...state, signIn: store.signIn, signOut: store.signOut }
}

/** Shows `children` only with a session; the login otherwise. Wrap the whole app or a single screen. */
export function RequireSession({ children, fallback }: { children: ReactNode; fallback?: ReactNode }) {
  const { status } = useSession()
  if (status === 'loading') return <>{fallback ?? <p className="muted">Comprobando sesión…</p>}</>
  if (status === 'signed_out') return <LoginScreen />
  return <>{children}</>
}
