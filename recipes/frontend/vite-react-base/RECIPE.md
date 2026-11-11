# vite-react-base

## Cuándo usarla

Para el **frontend de una app con backend propio en Python** (FastAPI): una SPA de Vite + React + TypeScript que llama directamente a la API. No sirve si necesitas SSR o SEO; en ese caso, Next.js.

No depende de otras recetas.

## Qué incluye

```
package.json            scripts: dev, dev:fake, build (tsc + vite), preview, typecheck, test
vite.config.ts          proxy /api → backend en dev y preview (BACKEND_URL); config de Vitest
tsconfig.json           strict, noUnused*
index.html
.env                    defaults públicos: VITE_API_MODE=http, VITE_API_URL=/api
.env.fake               VITE_API_MODE=fake (npm run dev:fake)
src/
  main.tsx              arranque: lee la config → construye los servicios con la factory → render
  config.ts             CONFIG: el ÚNICO sitio que lee import.meta.env
  vite-env.d.ts         tipos de las VITE_*
  App.tsx               raíz: recibe sus servicios desde fuera
  app-context.tsx       AppServices + useApp() (los servicios llegan por contexto)
  api/
    api.ts              type Api (el contrato) + ApiError + NetworkError
    types.ts            tipos de los datos que se intercambian con el backend
    http-client.ts      createHttpClient: base URL, Bearer, refresh y reintento en 401, errores tipados, stream()
    http-api.ts         createHttpApi(client): Api real (pasa de snake_case a camelCase)
    fake/fake-api.ts    createFakeApi(): Api en memoria
    make-api.ts         makeApi({mode}): factory que elige entre http y fake
  auth/token-provider.ts  TokenProvider (de dónde sale el token) + noAuth + staticToken
  hooks/use-load.ts     useLoad(load, deps): {data, loading, error, reload}, descarta respuestas obsoletas
  screens/HomeScreen.tsx  pantalla de ejemplo con sus tres estados
  styles/tokens.css     variables de diseño (claro y oscuro)
  styles/global.css
  test-setup.ts
  *.test.ts(x)          23 tests: cliente HTTP, factory, App con el fake, contraste WCAG de los tokens
```

## Decisiones

- **Vite + React y no Next.js.** El backend ya es Python. Next añadiría un servidor Node en medio, que es lo que hace aurora con sus `app/api/*/route.ts`.
- **La API es un tipo con dos implementaciones** (patrón de Vera-Symplia). `Api` define el contrato, y `createHttpApi` y `createFakeApi` lo cumplen. El fake usa `satisfies Api`, así que el compilador avisa si le falta un método. Ningún componente llama a `fetch`.
- **El backend se elige en la configuración.** `VITE_API_MODE=http|fake` y `makeApi` construye la implementación. Pasar a fake (para una demo, un e2e o trabajar sin backend) es cambiar una variable: `npm run dev:fake`. Un valor desconocido lanza un error, nunca un valor por defecto silencioso. El fake se carga con `import()`, así que es un chunk aparte que la app en modo `http` nunca descarga.
- **Los servicios llegan por contexto** (`useApp()`), no importando singletons. Así los tests montan los mismos componentes con un fake.
- **Cliente HTTP inyectable.** `fetcher` y `tokens` entran por opciones, así que se prueba sin red.
  - En un 401 renueva el token una sola vez y reintenta (como aurora y Vera). Si sigue fallando, llama a `onSessionExpired`.
  - Errores: `ApiError(status, code)` lee tanto `{"error": {"code"}}` como el `{"detail"}` de FastAPI. `NetworkError` cubre el caso sin conexión o un 5xx sin cuerpo.
  - Cancelar no se considera un error.
- **La auth queda detrás de `TokenProvider`.** Supabase, un JWT propio o nada: se cambia sin tocar el cliente. Hay un ejemplo con Supabase en el propio archivo.
- **El proxy de Vite** reenvía `/api` al backend: en desarrollo no hay CORS y el SSE pasa sin cambios. En producción, sirve el frontend en el mismo dominio que la API o cambia `VITE_API_URL`.
- **CSS con variables de diseño, sin framework.** Hay un test que comprueba el contraste WCAG AA de los pares texto/fondo (lo hace Vera).
- **Sin router ni librería de estado.** No había un patrón común: Vera tiene un router hecho a mano con el hash, ATI usa el de Angular y aurora el de Next. Si lo necesitas, añade `react-router`.

## Cómo adaptarla

1. Copia `files/` a `frontend/`. Sustituye `{{app_name}}` en `package.json`, `index.html` y `src/config.ts`. Después ejecuta `npm install`.
2. **Endpoints:** para añadir uno, pon el método en `Api` (`api/api.ts`), su tipo en `types.ts` y su implementación en `http-api.ts` y en `fake/fake-api.ts`. Si crecen mucho, sepáralos por grupos, como Vera: `http-api.users.ts` devuelve un `Pick<Api, ...>`.
3. **Auth:** escribe tu `TokenProvider` y pásalo en `main.tsx`. Que `onSessionExpired` lleve al login.
4. **Pantallas:** en `screens/` o en `features/<nombre>/`. Usa `useApp()` y `useLoad()`.
5. **Estilos:** cambia los valores de `tokens.css`. Si añades pares de color, inclúyelos en `tokens.test.ts`.
6. Desarrollo: `npm run dev` (con el backend en `BACKEND_URL`, por defecto `127.0.0.1:8000`) o `npm run dev:fake`. Para comprobar todo: `npm run typecheck && npm test && npm run build`.

**Dependencias** (probado con vite 8.3.8, react 19.3.1, typescript 7.0.2 y vitest 5.1.0): ya están en `package.json`.

## Origen

- Interfaz `Api` con implementaciones HTTP y falsa, elegida en el arranque y con el fake cargado por `import()`; servicios por contexto; cliente con dependencias inyectadas y renovación del token en 401; `ApiError` y `NetworkError`; `useLoad`; variables de diseño con test de contraste; proxy de Vite: Vera-Symplia.
- Renovar el token una vez en 401 y reintentar: aurora (`fetchWithAuth`).
- `TokenProvider` y el error por modo desconocido: nuevos, siguiendo la regla de no tener valores por defecto de los backends Python.
