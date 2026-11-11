/**
 * Where the bearer token comes from. The HTTP client only knows this interface, so the auth
 * system (Supabase, own JWT, none) is swapped without touching the client.
 *
 * Supabase, for example:
 *   const tokens: TokenProvider = {
 *     getToken: async () => (await supabase.auth.getSession()).data.session?.access_token ?? null,
 *     refresh: async () => (await supabase.auth.refreshSession()).data.session?.access_token ?? null,
 *   }
 */
export type TokenProvider = {
  /** Current access token, or null when signed out. */
  getToken(): Promise<string | null>
  /** Try to get a fresh token after a 401. Null = the session is over. */
  refresh(): Promise<string | null>
}

/** No auth (public API, or local dev without login). */
export const noAuth: TokenProvider = {
  getToken: async () => null,
  refresh: async () => null,
}

/** A fixed token. For tests and scripts. */
export function staticToken(token: string): TokenProvider {
  return { getToken: async () => token, refresh: async () => null }
}
