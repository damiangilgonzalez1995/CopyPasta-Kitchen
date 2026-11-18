# react-supabase-auth

## Cuándo usarla

Para **el login del frontend con Supabase Auth** (correo y contraseña): sesión guardada, token Bearer renovado solo, pantalla de login, guard que la enseña hasta que hay sesión y botón de salir. El proveedor se elige en `.env`: `supabase` en real y `fake` para desarrollar, demos y e2e sin Supabase.

No cubre magic link, OAuth, registro ni invitaciones: supabase-js los ofrece, pero cada uno es un flujo con callback y no estaban en más de un proyecto de origen.

**Requiere `vite-react-base`** (usa su `TokenProvider` y sus variables de diseño). **Usa `react-app-router`** (le pasa `RequireSession` como guard) y `playwright-e2e` (entra con la cuenta del fake).

## Qué incluye

```
src/auth/
  auth.ts              Auth (el contrato): getSession · signIn · signOut · refresh · onChange · AuthError(code) · tokenProviderOf(auth)
  settings.ts          bloque AuthSettings: authSettings(import.meta.env) → VITE_AUTH_PROVIDER (obligatorio), VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY
  supabase-auth.ts     createSupabaseAuth({url, anonKey, fetcher?}): supabase-js con sesión persistida y refresh automático
  fake-auth.ts         createFakeAuth({users?}): en memoria, sesión en localStorage; cuenta demo@example.com / demo
  make-auth.ts         makeAuth(settings): factory con import() por proveedor (supabase-js es un chunk aparte)
  session-store.ts     createSessionStore(auth): loading → signed_in | signed_out (+ expired), sin React
  session-context.tsx  SessionProvider · useSession() · RequireSession (el guard: login hasta que hay sesión)
  LoginScreen.tsx      correo + contraseña, mensaje por código, "Tu sesión ha caducado"
  SignOutButton.tsx    "Salir (correo)"
  auth.css             solo usa las variables de vite-react-base
  index.ts
  fake-gotrue.ts       Supabase Auth a nivel HTTP para tests: corre el supabase-js real, solo se sustituye fetch
  auth.test.ts         18 tests: conformidad de los dos proveedores, qué se envía a GoTrue, refresh revocado, 429/5xx, store, settings, factory
  session.test.tsx     4 tests: login → contenido, contraseña mal, sesión guardada, caducidad
```

## Decisiones

- **`Auth` es un tipo con dos implementaciones** (el patrón de `Api` en la base): `createSupabaseAuth` y `createFakeAuth`. `makeAuth` elige por `VITE_AUTH_PROVIDER` y un valor desconocido falla nombrándolo. Las dos van con `import()`: la build en modo fake no descarga supabase-js (217 kB) y la real no lleva el fake.
- **supabase-js, no la API REST a mano.** Hablar con GoTrue por `fetch` obliga a gestionar el refresh a mano (renovar 60 s antes, una sola promesa en vuelo, borrar la sesión si el refresh da 4xx). supabase-js hace todo eso con `persistSession` y `autoRefreshToken`; la receta solo añade el camino explícito `refresh()` para el 401 del cliente HTTP.
- **La sesión vive fuera de React** (`session-store.ts`). `main.tsx` lo construye una vez, le da `expire` al cliente HTTP (`onSessionExpired`) y el store a `<SessionProvider>`. Así el 401 que sobrevive al refresh (la "sesión zombie") vuelve al login con "Tu sesión ha caducado" sin que el cliente HTTP sepa nada de React.
- **El guard no conoce el router.** `RequireSession` pinta el login *en el sitio* del contenido y conserva la URL: tras entrar, el usuario ve lo que pidió. Con `react-app-router` se pasa como `guard` y protege todas las pantallas.
- **Solo el código del error llega a la pantalla.** `AuthError.code` ∈ `invalid_credentials | email_not_confirmed | rate_limited | unavailable`; el mensaje de supabase-js queda en `cause`.
- **`signOut` borra lo local primero** (`scope: 'local'`) y avisar a GoTrue es cortesía: si no hay red, se sale igual.
- **Un refresh rechazado cierra la sesión; un fallo de red no.** `refreshSession` con `AuthApiError` (token revocado, contraseña cambiada) borra la sesión; un 5xx o sin conexión devuelve `null` sin tocarla.
- **Rol y tenant no se leen del JWT.** Los proyectos de origen no decodifican claims en el navegador: el rol sale de `GET /me` (la `Identity` de la base) y el tenant lo saca el backend del token (`auth-verifier`). El frontend solo necesita `user.id` y `email`.
- **El fake persiste en localStorage**, como el real: una recarga mantiene la sesión y el e2e puede probarlo. Una cuenta por defecto; `users` para más.
- **Tests a nivel HTTP** (`fake-gotrue.ts`, como `FakeOpenAI` en `voice-providers`): corre el supabase-js real y se comprueba el grant, la `apikey` y el refresh token que se envían, y cómo se tratan las respuestas reales (`error_code`).

## Cómo adaptarla

1. Copia `files/` encima del frontend de `vite-react-base` y ejecuta `npm install @supabase/supabase-js@^2.119.0`.
2. **Settings:** en `config.ts` añade el bloque, igual que un `Settings(AuthSettings, ...)` del backend:

   ```ts
   import { authSettings } from './auth/settings'
   export const CONFIG = { ..., auth: authSettings(import.meta.env) } as const
   ```

   En `vite-env.d.ts` declara `VITE_AUTH_PROVIDER`, `VITE_SUPABASE_URL` y `VITE_SUPABASE_ANON_KEY` (las tres `?: string`). En `.env`: `VITE_AUTH_PROVIDER=supabase`, la URL del proyecto y la anon key (son públicas: RLS protege los datos). En `.env.fake`: `VITE_AUTH_PROVIDER=fake`.
3. **Arranque** (`main.tsx`):

   ```tsx
   const auth = await makeAuth(CONFIG.auth)
   const session = createSessionStore(auth)
   const api = await makeApi({ ..., tokens: tokenProviderOf(auth), onSessionExpired: session.expire })
   // render:
   <SessionProvider store={session}>
     <RequireSession><App services={{ api }} /></RequireSession>
   </SessionProvider>
   ```

   Con `react-app-router`: `createAppRouter({ guard: RequireSession, headerActions: <SignOutButton /> })` y `<App services router>` dentro de `<SessionProvider>`.
4. **Pantallas:** `useSession()` da `status`, `session.user`, `signOut`. El backend sigue siendo quien dice quién eres (`api.me()`).
5. **Proveedor nuevo** (JWT propio, Auth0): implementa `Auth`, añade el valor en `AuthProvider` y el caso en `makeAuth`, y pásalo por la batería `conformance(...)` de `auth.test.ts`.
6. Para comprobarla: `npm run typecheck && npm test` (22 tests de esta receta, 45 con la base).

**Dependencias:** `@supabase/supabase-js` (probado con 2.119).

## Origen

- Probado en producción: `Api` con sesión dentro (`hasSession`, `login`, `logout`), refresh una vez en 401 y después `onSessionExpired`, login en el sitio del contenido, "Tu sesión ha caducado", salir borrando lo local y avisando por cortesía, un refresh con 4xx cierra la sesión y con 5xx no, fake de auth con contraseña incorrecta y sesión persistida, cliente probado inyectando `fetcher` y `storage`; supabase-js con `getSession` + `onAuthStateChange`, `signInWithPassword`, errores como claves estables, 401 con sesión viva = cerrar sesión, guard que espera la comprobación inicial; tokens en localStorage validados con `getMe()` al arrancar.
- Nuevo en esta receta: `session-store.ts` fuera de React, `fake-gotrue.ts` y el proveedor elegido en settings, siguiendo la base.
