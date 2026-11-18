import { describe, expect, it } from 'vitest'

import { AuthError, tokenProviderOf, type Auth } from './auth'
import { createFakeAuth } from './fake-auth'
import { FakeGoTrue } from './fake-gotrue'
import { makeAuth } from './make-auth'
import { createSessionStore } from './session-store'
import { authSettings } from './settings'
import { createSupabaseAuth } from './supabase-auth'

const ANA = { email: 'ana@example.com', password: 'secret' }

/** What every `Auth` must do. A new provider = one more `describe` with its builder. */
function conformance(name: string, build: () => Auth) {
  describe(`${name} conformance`, () => {
    it('starts signed out and signs in with email and password', async () => {
      const auth = build()
      expect(await auth.getSession()).toBeNull()
      const session = await auth.signIn(ANA)
      expect(session.accessToken).toBeTruthy()
      expect(session.user.email).toBe(ANA.email)
      expect(await auth.getSession()).toEqual(session)
    })

    it('rejects a wrong password with a code, never the provider message', async () => {
      const auth = build()
      const error = await auth.signIn({ ...ANA, password: 'wrong' }).catch((reason: unknown) => reason)
      expect(error).toBeInstanceOf(AuthError)
      expect((error as AuthError).code).toBe('invalid_credentials')
      expect(String(error)).not.toContain('Invalid login')
    })

    it('keeps the session across instances (a reload) and clears it on sign out', async () => {
      await build().signIn(ANA)
      const again = build()
      expect((await again.getSession())?.user.email).toBe(ANA.email)
      await again.signOut()
      expect(await again.getSession()).toBeNull()
      expect(await build().getSession()).toBeNull()
    })

    it('refreshes to a new token and tells listeners', async () => {
      const auth = build()
      const seen: (string | null)[] = []
      const stop = auth.onChange((session) => seen.push(session?.accessToken ?? null))
      const first = (await auth.signIn(ANA)).accessToken
      const refreshed = await auth.refresh()
      expect(refreshed?.accessToken).toBeTruthy()
      expect(refreshed?.accessToken).not.toBe(first)
      await auth.signOut()
      stop()
      expect(seen).toContain(first)
      expect(seen[seen.length - 1]).toBeNull()
    })

    it('refresh without a session is null, not an error', async () => {
      expect(await build().refresh()).toBeNull()
    })

    it('is a TokenProvider for the HTTP client', async () => {
      const auth = build()
      const tokens = tokenProviderOf(auth)
      expect(await tokens.getToken()).toBeNull()
      const { accessToken } = await auth.signIn(ANA)
      expect(await tokens.getToken()).toBe(accessToken)
      expect(await tokens.refresh()).not.toBeNull()
    })
  })
}

conformance('fake auth', () => createFakeAuth({ users: [{ id: 'u-ana', ...ANA }], latencyMs: 0 }))

const gotrue = { current: new FakeGoTrue() }
conformance('supabase auth', () => createSupabaseAuth({ url: 'http://localhost:54321', anonKey: 'anon-key', fetcher: gotrue.current.fetch }))

describe('supabase auth over HTTP', () => {
  const build = (server: FakeGoTrue) => createSupabaseAuth({ url: 'http://localhost:54321', anonKey: 'anon-key', fetcher: server.fetch })

  it('sends the password grant with the anon key and the refresh grant with the refresh token', async () => {
    const server = new FakeGoTrue()
    const auth = build(server)
    await auth.signIn({ email: '  Ana@example.com '.toLowerCase(), password: 'secret' })
    await auth.refresh()
    const [login, refresh] = server.requests.filter((r) => r.path.endsWith('/token'))
    expect(login).toMatchObject({ grant: 'password', apikey: 'anon-key', body: { email: 'ana@example.com', password: 'secret' } })
    expect(refresh.grant).toBe('refresh_token')
    expect(String(refresh.body.refresh_token)).toMatch(/^refresh-/)
  })

  it('a refresh token GoTrue rejects ends the session', async () => {
    const accepted = new Set<string>()
    const auth = build(new FakeGoTrue({ refreshTokens: accepted }))
    await auth.signIn(ANA)
    accepted.clear() // revoked on the server (signed out elsewhere, password changed)
    expect(await auth.refresh()).toBeNull()
    expect(await auth.getSession()).toBeNull()
  })

  it('maps 429 and 5xx to codes without the message', async () => {
    const limited = await build(new FakeGoTrue({ failWith: 429 })).signIn(ANA).catch((reason: unknown) => reason as AuthError)
    expect(limited).toMatchObject({ code: 'rate_limited' })
    const down = await build(new FakeGoTrue({ failWith: 503 })).signIn(ANA).catch((reason: unknown) => reason as AuthError)
    expect(down).toMatchObject({ code: 'unavailable' })
    expect(String(down)).not.toContain('secret details')
  })
})

describe('session store', () => {
  it('goes loading -> signed_out -> signed_in -> expired', async () => {
    const auth = createFakeAuth({ latencyMs: 0 })
    const store = createSessionStore(auth)
    const statuses: string[] = []
    store.subscribe(() => statuses.push(store.getState().status))
    expect(store.getState().status).toBe('loading')
    const stop = await store.start()
    expect(store.getState().status).toBe('signed_out')
    await store.signIn({ email: 'demo@example.com', password: 'demo' })
    expect(store.getState()).toMatchObject({ status: 'signed_in', expired: false })
    store.expire()
    expect(store.getState()).toMatchObject({ status: 'signed_out', session: null, expired: true })
    expect(await auth.getSession()).toBeNull()
    await store.signIn({ email: 'demo@example.com', password: 'demo' })
    expect(store.getState().expired).toBe(false)
    stop()
    expect(statuses).toEqual(['signed_out', 'signed_in', 'signed_in', 'signed_out', 'signed_out', 'signed_in', 'signed_in'])
  })

  it('follows a sign out made elsewhere (another tab)', async () => {
    const auth = createFakeAuth({ latencyMs: 0 })
    const store = createSessionStore(auth)
    await store.start()
    await auth.signIn({ email: 'demo@example.com', password: 'demo' })
    expect(store.getState().status).toBe('signed_in')
    await auth.signOut()
    expect(store.getState().status).toBe('signed_out')
  })
})

describe('settings and factory', () => {
  it('requires the provider and the supabase keys', async () => {
    expect(() => authSettings({})).toThrow('VITE_AUTH_PROVIDER')
    expect(() => authSettings({ VITE_AUTH_PROVIDER: 'supabase' })).toThrow('VITE_SUPABASE_URL')
    expect(authSettings({ VITE_AUTH_PROVIDER: 'fake' })).toEqual({ provider: 'fake' })
    const auth = await makeAuth(authSettings({ VITE_AUTH_PROVIDER: 'fake' }))
    expect((await auth.signIn({ email: 'demo@example.com', password: 'demo' })).user.email).toBe('demo@example.com')
    const supabase = await makeAuth({ provider: 'supabase', supabaseUrl: 'http://localhost:54321', supabaseAnonKey: 'k' })
    expect(await supabase.getSession()).toBeNull()
  })
})
