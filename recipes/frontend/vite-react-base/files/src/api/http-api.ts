/** The real implementation of `Api`, over the HTTP client. Maps backend payloads (snake_case) to app types. */

import type { Api } from './api'
import type { HttpClient } from './http-client'
import type { Identity } from './types'

type IdentityBody = { user_id: string; tenant_id: string; name: string }

export function createHttpApi(client: HttpClient): Api {
  return {
    async me(): Promise<Identity> {
      const body = await client.get<IdentityBody>('/me')
      return { userId: body.user_id, tenantId: body.tenant_id, name: body.name }
    },
  }
}
