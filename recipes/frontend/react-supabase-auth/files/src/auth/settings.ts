/**
 * Settings block of the auth capability. `config.ts` mixes it in (`auth: authSettings(import.meta.env)`),
 * the same way a backend `Settings` inherits `AuthSettings`. Only `config.ts` reads `import.meta.env`.
 */

export type AuthProvider = 'supabase' | 'fake'

export type AuthSettings = {
  provider: AuthProvider
  supabaseUrl?: string
  supabaseAnonKey?: string
}

type AuthEnv = {
  readonly VITE_AUTH_PROVIDER?: string
  readonly VITE_SUPABASE_URL?: string
  readonly VITE_SUPABASE_ANON_KEY?: string
}

export function authSettings(env: AuthEnv): AuthSettings {
  const provider = env.VITE_AUTH_PROVIDER
  // No silent default: a typo must not ship a fake login to production.
  if (provider !== 'supabase' && provider !== 'fake') {
    throw new Error(`VITE_AUTH_PROVIDER must be "supabase" or "fake", got ${JSON.stringify(provider)}`)
  }
  if (provider === 'supabase' && !(env.VITE_SUPABASE_URL && env.VITE_SUPABASE_ANON_KEY)) {
    throw new Error('VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are required when VITE_AUTH_PROVIDER=supabase')
  }
  return { provider, supabaseUrl: env.VITE_SUPABASE_URL, supabaseAnonKey: env.VITE_SUPABASE_ANON_KEY }
}
