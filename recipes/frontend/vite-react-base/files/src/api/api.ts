/**
 * The API contract of the app. Components only know this type; never `fetch`.
 *
 * Two implementations satisfy it: `createHttpApi` (the real backend) and `createFakeApi` (in memory).
 * `makeApi` picks one from the settings (VITE_API_MODE). Add an endpoint = a method here, then in both.
 */

import type { Identity } from './types'

/** The backend answered with an error status. `code` is stable and machine-readable; show messages by code. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly details?: unknown,
  ) {
    super(`API error ${status}: ${code}`)
    this.name = 'ApiError'
  }

  get isUnauthorized(): boolean {
    return this.status === 401
  }
}

/** The request never got an answer (offline, DNS, CORS, 5xx without body). Usually worth a retry. */
export class NetworkError extends Error {
  constructor(readonly cause?: unknown) {
    super('Network error')
    this.name = 'NetworkError'
  }
}

export type Api = {
  /** Who is signed in. */
  me(): Promise<Identity>
}
