/**
 * Supabase Auth (GoTrue) at the HTTP level for tests: the real supabase-js runs, only `fetch` is replaced.
 * That way the tests check what is actually sent (grant type, apikey, refresh token) and how real answers
 * (session JSON, `error_code`) are handled. Not shipped: it is only imported by tests.
 */

export type FakeGoTrueOptions = {
  users?: Record<string, string> // email -> password
  /** Answers every request with this status (to simulate 429 or 503). */
  failWith?: number
  /** Refresh tokens that GoTrue still accepts. */
  refreshTokens?: Set<string>
}

export class FakeGoTrue {
  readonly requests: { path: string; grant: string | null; apikey: string | null; body: Record<string, unknown> }[] = []
  private readonly users: Record<string, string>
  private readonly refreshTokens: Set<string>
  private counter = 0

  constructor(private readonly options: FakeGoTrueOptions = {}) {
    this.users = options.users ?? { 'ana@example.com': 'secret' }
    this.refreshTokens = options.refreshTokens ?? new Set()
  }

  /** Pass as `fetcher` to `createSupabaseAuth`. */
  readonly fetch: typeof fetch = async (input, init) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url)
    const headers = new Headers(init?.headers)
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {}
    this.requests.push({ path: url.pathname, grant: url.searchParams.get('grant_type'), apikey: headers.get('apikey'), body })

    if (this.options.failWith) return error(this.options.failWith, 'unexpected_failure', 'nope: secret details')
    if (url.pathname.endsWith('/token')) {
      if (url.searchParams.get('grant_type') === 'password') {
        const email = String(body.email)
        if (this.users[email] !== body.password) return error(400, 'invalid_credentials', 'Invalid login credentials')
        return json(this.session(email))
      }
      if (url.searchParams.get('grant_type') === 'refresh_token') {
        const token = String(body.refresh_token)
        if (!this.refreshTokens.delete(token)) return error(400, 'refresh_token_not_found', 'Invalid Refresh Token')
        return json(this.session(token.split(':')[1]))
      }
    }
    if (url.pathname.endsWith('/logout')) return new Response(null, { status: 204 })
    if (url.pathname.endsWith('/user')) return json(this.user(String(headers.get('authorization')).split(':')[1] ?? ''))
    return error(404, 'not_found', url.pathname)
  }

  private session(email: string) {
    const refresh = `refresh-${++this.counter}:${email}`
    this.refreshTokens.add(refresh)
    const now = Math.floor(Date.now() / 1000)
    return {
      access_token: jwt({ sub: this.user(email).id, email, role: 'authenticated', aud: 'authenticated', exp: now + 3600, iat: now, jti: this.counter }),
      token_type: 'bearer',
      expires_in: 3600,
      expires_at: now + 3600,
      refresh_token: refresh,
      user: this.user(email),
    }
  }

  private user(email: string) {
    return { id: `id-${email}`, aud: 'authenticated', role: 'authenticated', email, app_metadata: {}, user_metadata: {}, created_at: '' }
  }
}

/** A token with the shape of a JWT (supabase-js reads `exp` from it). Unsigned: only for tests. */
function jwt(claims: Record<string, unknown>): string {
  const part = (value: unknown) => btoa(JSON.stringify(value)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `${part({ alg: 'HS256', typ: 'JWT' })}.${part(claims)}.sig`
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status, headers: { 'content-type': 'application/json' } })
}

function error(status: number, code: string, msg: string): Response {
  return new Response(JSON.stringify({ code: status, error_code: code, msg }), {
    status,
    headers: { 'content-type': 'application/json', 'x-sb-error-code': code },
  })
}
