/**
 * In-memory `Auth`: the app signs in with no Supabase (VITE_AUTH_PROVIDER=fake). Used by demos, tests and e2e.
 * The session is kept in `storage` (localStorage by default) so a reload keeps you signed in, like the real one.
 */

import { AuthError, type Auth, type Credentials, type Session } from './auth'

export type FakeUser = Credentials & { id?: string }

export type FakeAuthOptions = {
  /** Accounts that can sign in. Default: `demo@example.com` / `demo`. */
  users?: FakeUser[]
  storage?: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
  storageKey?: string
  /** Simulated latency in ms. 0 in tests. */
  latencyMs?: number
}

export const FAKE_USER: FakeUser = { id: 'user-1', email: 'demo@example.com', password: 'demo' }

export function createFakeAuth(options: FakeAuthOptions = {}): Auth {
  const { users = [FAKE_USER], storageKey = 'fake-auth.session', latencyMs = 100 } = options
  const storage = options.storage ?? memoryStorage()
  const listeners = new Set<(session: Session | null) => void>()
  const wait = () => new Promise((resolve) => setTimeout(resolve, latencyMs))
  let issued = 0

  function read(): Session | null {
    try {
      const raw = storage.getItem(storageKey)
      return raw ? (JSON.parse(raw) as Session) : null
    } catch {
      return null
    }
  }

  function write(session: Session | null) {
    if (session) storage.setItem(storageKey, JSON.stringify(session))
    else storage.removeItem(storageKey)
    listeners.forEach((listener) => listener(session))
  }

  return {
    async getSession() {
      return read()
    },

    async signIn({ email, password }) {
      await wait()
      const user = users.find((candidate) => candidate.email === email.trim().toLowerCase())
      if (!user || user.password !== password) throw new AuthError('invalid_credentials')
      const session: Session = {
        accessToken: `fake-token-${++issued}`,
        user: { id: user.id ?? `user-${user.email}`, email: user.email },
      }
      write(session)
      return session
    },

    async signOut() {
      write(null)
    },

    async refresh() {
      const current = read()
      if (!current) return null
      const session = { ...current, accessToken: `fake-token-${++issued}` }
      write(session)
      return session
    },

    onChange(listener) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
  }
}

function memoryStorage(): Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> {
  if (typeof localStorage !== 'undefined') return localStorage
  const map = new Map<string, string>()
  return {
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => void map.set(key, value),
    removeItem: (key) => void map.delete(key),
  }
}
