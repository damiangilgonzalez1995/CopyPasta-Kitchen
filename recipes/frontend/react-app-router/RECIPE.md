# react-app-router

## Cuándo usarla

Para **una SPA con varias pantallas**: tabla de rutas en un solo sitio, cabecera con navegación, pantallas perezosas (un chunk por pantalla), 404 y pantalla de error. El guard de sesión y las acciones de la cabecera entran desde `main.tsx`, así que el router no conoce la auth.

Con una sola pantalla no hace falta: la base ya pinta `HomeScreen` sin router.

**Requiere `vite-react-base`** (sustituye su `App.tsx`). **Usa `react-supabase-auth`** (`RequireSession` como guard) y `playwright-e2e`.

## Qué incluye

```
src/router/
  routes.tsx         PATHS · appRoutes({guard?, headerActions?}) → RouteObject[] · createAppRouter({kind: 'browser' | 'hash'})
  Layout.tsx         cabecera (nombre, NavLink por ruta, acciones) + <Outlet>
  NotFoundScreen.tsx 404 con enlace al inicio
  ErrorScreen.tsx    error boundary de ruta: título, solo la clase del error, botón Recargar
  router.css         solo usa las variables de vite-react-base
  index.ts
  router.test.tsx    5 tests: navegación y enlace activo, pantalla perezosa por URL, 404 y vuelta, guard y acciones, error sin internos
src/screens/SettingsScreen.tsx   ejemplo de pantalla perezosa
src/App.tsx          sustituye al de la base: <AppProvider><RouterProvider router/></AppProvider>
src/App.test.tsx     sustituye al de la base: los mismos 4 tests, montando el router en memoria
```

## Decisiones

- **react-router en modo data** (`createBrowserRouter` + `RouterProvider`), no `<Routes>` anidadas. Las rutas son datos (`RouteObject[]`), así que `createMemoryRouter(appRoutes(), {initialEntries})` las monta en un test sin DOM de navegador, y `lazy` las trocea por pantalla. No había un patrón común en los proyectos de origen; la receta toma de ellos la tabla declarativa con guard por rama y que la sesión decida antes que la ruta.
- **El guard y las acciones se inyectan.** `appRoutes({guard, headerActions})` recibe un componente que envuelve el layout y un nodo para la cabecera. `router/` no importa `auth/`; `main.tsx`, un nivel por encima, los junta. Sin auth, no se pasa nada y la app es pública.
- **`PATHS` como constantes.** Enlaces, `navigate` y tests usan `PATHS.settings`, no `'/settings'` escrito a mano.
- **Una ruta perezosa como ejemplo.** `lazy: async () => ({ Component })` saca `SettingsScreen` a su propio chunk; se descarga la primera vez que se visita.
- **404 dentro del layout y error boundary de ruta.** `*` pinta `NotFoundScreen` con la cabecera; una pantalla que lanza al renderizar muestra `ErrorScreen` con la *clase* del error y un botón de recargar, nunca el mensaje (puede llevar internos).
- **`browser` por defecto, `hash` si el host no reenvía a `index.html`.** `vite preview` y cualquier host de SPA responden `index.html` a cualquier ruta; en un bucket estático sin fallback, `createAppRouter({ kind: 'hash' })`.

## Cómo adaptarla

1. Copia `files/` encima del frontend de `vite-react-base` (sobrescribe `App.tsx` y `App.test.tsx`) y ejecuta `npm install react-router@^8.5.1`.
2. **Arranque** (`main.tsx`):

   ```tsx
   import { createAppRouter } from './router'
   const router = createAppRouter()                       // público
   const router = createAppRouter({ guard: RequireSession, headerActions: <SignOutButton /> })  // con react-supabase-auth
   // render: <App services={{ api }} router={router} />
   ```

3. **Una pantalla nueva:** su ruta en `PATHS`, su entrada en `children` de `appRoutes` (`lazy` si pesa) y su `NavLink` en `Layout.tsx`. Para `react-agent-chat`: añade `chat: ChatApi` a `AppServices`, constrúyelo en `main.tsx` junto a `api` y una `ChatScreen` que haga `<ChatView chat={useApp().chat} />`.
4. **Rutas con parámetros:** `path: 'documents/:id'` y `useParams()` en la pantalla. Declara las literales antes que las dinámicas (`documents/new` antes de `documents/:id`).
5. **Pantallas por rol:** envuelve la rama con otro guard (`({children}) => role === 'admin' ? children : <Navigate to={PATHS.home} />`) o pasa un guard distinto a `appRoutes`. El backend sigue siendo la barrera real (en producción, el guard deja pasar si no pudo cargar las capacidades, para no entrar en bucle).
6. Para comprobarla: `npm run typecheck && npm test` (9 tests de esta receta, 28 con la base).

**Dependencias:** `react-router` (probado con 8.5.1).

## Origen

- Probado en producción: tabla de rutas declarativa con guard en la rama protegida, rutas literales antes que dinámicas, `**` a una pantalla, `loadChildren` por feature; la sesión decide antes que la ruta, constantes de ruta, router por hash, tests de `navigate` con un `vi.fn()` y e2e con `toHaveURL`.
- Nuevo en esta receta: guard inyectado desde arriba, error boundary de ruta y pantalla perezosa, siguiendo la regla de que las capacidades no se importan entre sí.
