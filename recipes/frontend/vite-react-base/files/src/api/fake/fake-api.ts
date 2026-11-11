/**
 * In-memory implementation of `Api`: the app runs with no backend (VITE_API_MODE=fake).
 * Used by demos, tests and e2e. Loaded with a dynamic import: it is a separate chunk that an `http` app never downloads.
 */

import type { Api } from '../api'
import type { Identity } from '../types'

export type FakeApiOptions = {
  /** Simulated latency in ms. 0 in tests. */
  latencyMs?: number
  identity?: Identity
}

export const FAKE_IDENTITY: Identity = { userId: 'user-1', tenantId: 'tenant-1', name: 'Demo User' }

export function createFakeApi(options: FakeApiOptions = {}): Api {
  const { latencyMs = 200, identity = FAKE_IDENTITY } = options
  const wait = () => new Promise((resolve) => setTimeout(resolve, latencyMs))

  // `satisfies` (not `as`): the compiler fails if the fake misses a method of Api.
  const api = {
    async me() {
      await wait()
      return identity
    },
  } satisfies Api
  return api
}
