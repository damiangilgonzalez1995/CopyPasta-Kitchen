# playwright-e2e

## Cuándo usarla

Para **probar el frontend de punta a punta en un navegador real sin backend ni Supabase**: Playwright compila la app en modo fake, la sirve con `vite preview` y recorre login, navegación y pantallas en escritorio y móvil. Corre en CI en cada push con un workflow incluido.

No cubre el e2e contra el stack real (backend + base de datos + Supabase local): Vera y ATI lo tienen, cada uno con su arranque (uv + Postgres, docker compose + `supabase start`) y ninguno lo ejecuta en CI. Si lo necesitas, es otra configuración con `testDir: 'e2e-real'` y el mismo Playwright.

**Requiere `vite-react-base`, `react-supabase-auth` y `react-app-router`**: los specs entran con la cuenta del fake y navegan por las rutas de la receta. Sin auth, borra `login.spec.ts` y el login de `enter()`; sin router, borra `navigation.spec.ts`.

## Qué incluye

```
playwright.config.ts            webServer: vite build --mode fake + vite preview; puerto derivado del cwd; proyectos desktop y phone; traza y captura solo al fallar
e2e/
  helpers.ts                    DEMO (cuenta del fake) · enter(page, path) · failOnConsoleErrors(page)
  home.spec.ts                  la home muestra los datos del fake sin errores de consola
  login.spec.ts                 contraseña mal → mensaje; la sesión sobrevive a una recarga; salir la termina
  navigation.spec.ts            enlaces, atrás, deep link, 404 y vuelta; el login conserva la URL pedida
.github/workflows/frontend.yml  npm ci → typecheck → test → build → playwright install chromium → e2e; informe como artefacto si falla
```

Scripts que añade a `package.json`: `e2e`, `e2e:ui`, `e2e:install`.

## Decisiones

- **Contra la build en modo fake, no contra `vite dev`.** `vite build --mode fake` carga `.env.fake` (`VITE_API_MODE=fake`, `VITE_AUTH_PROVIDER=fake`) y `vite preview` sirve lo mismo que irá a producción, con fallback a `index.html` para los deep links (Vera). Así el e2e prueba el bundle real y no depende de red.
- **Puerto derivado del cwd** (`40000 + sha1(cwd) % 10000`, Vera): dos checkouts o worktrees pueden correr a la vez; `E2E_PORT` lo fija. `--host 127.0.0.1` porque `vite preview` sin `--host` escucha en `localhost`, que en Windows resuelve a IPv6 y Playwright esperaría para siempre.
- **Dos proyectos, escritorio y móvil** (Vera `desktop`/`phone`, ATI `escritorio`/`movil`): el mismo spec corre en los dos; un layout que se rompe en 412 px se ve aquí.
- **Helpers como funciones, no page objects** (Vera, ATI): `enter(page)` hace el login con la cuenta del fake y un spec se lee de arriba abajo. Los selectores son de accesibilidad (`getByRole`, `getByLabel`), los mismos que usan los tests de Vitest.
- **Cualquier error de consola hace fallar el test** (`failOnConsoleErrors`, de ATI `attachConsoleErrorRecorder`): un warning de React o una promesa sin capturar no pasan desapercibidos.
- **Traza y captura solo al fallar, reintentos solo en CI** (ATI). El informe HTML se sube como artefacto si el job falla.
- **El e2e sí corre en CI.** Ni Vera ni ATI lo ejecutan en cada push (ATI solo a mano contra el stack real). Como esta receta no necesita nada externo, no hay motivo para dejarlo fuera: dura menos de un minuto.

## Cómo adaptarla

1. Copia `files/` en la raíz del frontend (el workflow va en `.github/workflows/` del repo; ajusta `paths` y `working-directory` si el frontend no está en `frontend/`). Ejecuta `npm install -D @playwright/test@^1.65.1 && npx playwright install chromium`.
2. En `package.json` añade `"e2e": "playwright test"`, `"e2e:ui": "playwright test --ui"` y `"e2e:install": "playwright install chromium"`. En `tsconfig.json` incluye `"e2e"` y `"playwright.config.ts"` para que `typecheck` los cubra. En `.gitignore`: `e2e/.results`, `e2e/.report`, `dist-fake`.
3. **Un spec nuevo:** `e2e/<pantalla>.spec.ts` que empiece por `await enter(page, PATH)`. Si la pantalla necesita datos, dáselos al fake (`createFakeApi({...})` lee opciones; para escenarios por spec, Vera guarda uno en `localStorage` con `page.addInitScript` antes de `goto` y el fake lo lee al arrancar).
4. **Chat (`react-agent-chat`):** con la ruta `/chat` montada, un spec escribe en el `textbox`, pulsa Enter y espera el texto que emite `createFakeChatApi`; cancelar y "Nueva conversación" se prueban igual.
5. Para comprobarla: `npm run e2e` (10 tests, 5 por proyecto, ~35 s). `npm run e2e:ui` para verlos en el navegador.

**Dependencias:** `@playwright/test` (probado con 1.65.1 y Chromium 1255).

## Origen

- `webServer` que compila en modo fake y sirve con `vite preview`, puerto derivado del cwd, proyectos escritorio y móvil, helpers como funciones (`open`, `enter`), specs de login con contraseña mal, de sesión que sobrevive a la recarga y de rutas con `toHaveURL`: Vera-Symplia (`playwright.config.ts`, `e2e/conversation.helpers.ts`, `e2e/technician.spec.ts`, `e2e-real/login.spec.ts`).
- `trace: retain-on-failure`, captura solo al fallar, reintentos solo en CI, informe HTML como artefacto, errores de consola que hacen fallar el test, `loginAs` por `getByLabel`: ATI_PLATFORM (`playwright.config.ts`, `e2e/helpers/auth.helpers.ts`, `.github/workflows/e2e.yml`).
- E2E en modo fake dentro del CI de cada push y `--host 127.0.0.1`: nuevos.
