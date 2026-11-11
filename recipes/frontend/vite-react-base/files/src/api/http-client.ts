/**
 * Low-level HTTP client: base URL, bearer token, one refresh-and-retry on 401, typed errors.
 * Every dependency comes in by option (`fetcher`, `tokens`), so it is tested without a network.
 */

import type { TokenProvider } from '../auth/token-provider'
import { noAuth } from '../auth/token-provider'
import { ApiError, NetworkError } from './api'

export type HttpClientOptions = {
  baseUrl: string
  tokens?: TokenProvider
  /** Called once when a 401 survives the refresh: sign out, go to login... */
  onSessionExpired?: () => void
  fetcher?: typeof fetch
}

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export function createHttpClient(options: HttpClientOptions) {
  const { baseUrl, tokens = noAuth, onSessionExpired } = options
  const fetcher = options.fetcher ?? ((input, init) => fetch(input, init))

  async function send(method: Method, path: string, body: unknown, signal: AbortSignal | undefined, token: string | null) {
    const headers: Record<string, string> = { Accept: 'application/json' }
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    if (token) headers.Authorization = `Bearer ${token}`
    try {
      return await fetcher(`${baseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal,
      })
    } catch (error) {
      if (signal?.aborted) throw error // a cancel is not a network failure
      throw new NetworkError(error)
    }
  }

  /** Sends the request; on 401 refreshes the token ONCE and retries. Returns only 2xx responses. */
  async function call(method: Method, path: string, body?: unknown, signal?: AbortSignal): Promise<Response> {
    let response = await send(method, path, body, signal, await tokens.getToken())
    if (response.status === 401) {
      const fresh = await tokens.refresh()
      if (fresh) response = await send(method, path, body, signal, fresh)
      if (response.status === 401) onSessionExpired?.()
    }
    if (!response.ok) throw await toError(response)
    return response
  }

  async function json<T>(method: Method, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    const response = await call(method, path, body, signal)
    if (response.status === 204) return undefined as T
    return (await response.json()) as T
  }

  return {
    get: <T>(path: string, signal?: AbortSignal) => json<T>('GET', path, undefined, signal),
    post: <T>(path: string, body?: unknown, signal?: AbortSignal) => json<T>('POST', path, body, signal),
    put: <T>(path: string, body?: unknown, signal?: AbortSignal) => json<T>('PUT', path, body, signal),
    patch: <T>(path: string, body?: unknown, signal?: AbortSignal) => json<T>('PATCH', path, body, signal),
    delete: <T>(path: string, signal?: AbortSignal) => json<T>('DELETE', path, undefined, signal),
    /** POST that returns the raw body stream (SSE). Same auth and errors as the rest. */
    stream: async (path: string, body: unknown, signal?: AbortSignal): Promise<ReadableStream<Uint8Array>> => {
      const response = await call('POST', path, body, signal)
      if (!response.body) throw new NetworkError('empty stream')
      return response.body
    },
  }
}

export type HttpClient = ReturnType<typeof createHttpClient>

/**
 * Error body: `{"error": {"code", "details"}}` or FastAPI's `{"detail": ...}`.
 * A 5xx without a readable body is a NetworkError (a proxy or crash, not an answer of the API).
 */
async function toError(response: Response): Promise<Error> {
  let body: unknown
  try {
    body = await response.json()
  } catch {
    if (response.status >= 500) return new NetworkError(`HTTP ${response.status}`)
    return new ApiError(response.status, `http_${response.status}`)
  }
  const record = (body ?? {}) as Record<string, unknown>
  const error = record.error as { code?: string; details?: unknown } | undefined
  if (error?.code) return new ApiError(response.status, error.code, error.details)
  const detail = record.detail as { code?: string } | string | undefined
  if (detail && typeof detail === 'object' && detail.code) return new ApiError(response.status, detail.code, detail)
  return new ApiError(response.status, `http_${response.status}`, detail ?? body)
}
