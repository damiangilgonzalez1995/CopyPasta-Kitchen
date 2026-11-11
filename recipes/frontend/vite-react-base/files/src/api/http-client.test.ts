import { describe, expect, it, vi, type Mock } from 'vitest'

import type { TokenProvider } from '../auth/token-provider'
import { staticToken } from '../auth/token-provider'
import { ApiError, NetworkError } from './api'
import { createHttpApi } from './http-api'
import { createHttpClient } from './http-client'

const json = (status: number, body?: unknown) =>
  new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

function clientWith(answers: Response[], tokens: TokenProvider = staticToken('t1'), onSessionExpired = vi.fn()) {
  const fetcher = vi.fn<typeof fetch>(async () => answers.shift() ?? json(500))
  const client = createHttpClient({ baseUrl: '/api', tokens, fetcher, onSessionExpired })
  return { client, fetcher, onSessionExpired }
}

const authHeader = (fetcher: Mock<typeof fetch>, call: number) =>
  (fetcher.mock.calls[call][1] as RequestInit & { headers: Record<string, string> }).headers.Authorization

describe('http client', () => {
  it('sends the bearer token and parses json', async () => {
    const { client, fetcher } = clientWith([json(200, { ok: true })])

    expect(await client.get('/ping')).toEqual({ ok: true })
    expect(fetcher.mock.calls[0][0]).toBe('/api/ping')
    expect(authHeader(fetcher, 0)).toBe('Bearer t1')
  })

  it('refreshes once on 401 and retries with the new token', async () => {
    const tokens: TokenProvider = { getToken: async () => 'old', refresh: async () => 'new' }
    const { client, fetcher, onSessionExpired } = clientWith([json(401), json(200, { ok: 1 })], tokens)

    expect(await client.get('/x')).toEqual({ ok: 1 })
    expect(fetcher).toHaveBeenCalledTimes(2)
    expect(authHeader(fetcher, 1)).toBe('Bearer new')
    expect(onSessionExpired).not.toHaveBeenCalled()
  })

  it('reports the session as expired when the refresh does not help', async () => {
    const { client, onSessionExpired } = clientWith([json(401)])

    await expect(client.get('/x')).rejects.toMatchObject({ status: 401 })
    expect(onSessionExpired).toHaveBeenCalledOnce()
  })

  it('maps error bodies to ApiError codes (own format and FastAPI detail)', async () => {
    const { client } = clientWith([
      json(409, { error: { code: 'already_exists', details: { id: 1 } } }),
      json(429, { detail: { code: 'quota_exceeded' } }),
      json(422, { detail: 'bad input' }),
    ])

    await expect(client.post('/a', {})).rejects.toEqual(new ApiError(409, 'already_exists', { id: 1 }))
    await expect(client.post('/b', {})).rejects.toMatchObject({ code: 'quota_exceeded' })
    await expect(client.post('/c', {})).rejects.toMatchObject({ code: 'http_422', details: 'bad input' })
  })

  it('turns a failed fetch and an unreadable 5xx into NetworkError', async () => {
    const offline = createHttpClient({ baseUrl: '', fetcher: async () => Promise.reject(new TypeError('offline')) })
    await expect(offline.get('/x')).rejects.toBeInstanceOf(NetworkError)

    const { client } = clientWith([new Response('<html>bad gateway</html>', { status: 502 })])
    await expect(client.get('/x')).rejects.toBeInstanceOf(NetworkError)
  })

  it('does not turn a cancel into a NetworkError', async () => {
    const controller = new AbortController()
    const fetcher = async () => {
      controller.abort()
      throw new DOMException('aborted', 'AbortError')
    }
    const client = createHttpClient({ baseUrl: '', fetcher })
    await expect(client.get('/x', controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('http api maps snake_case payloads to app types', async () => {
    const { client } = clientWith([json(200, { user_id: 'u', tenant_id: 't', name: 'Ana' })])
    expect(await createHttpApi(client).me()).toEqual({ userId: 'u', tenantId: 't', name: 'Ana' })
  })
})
