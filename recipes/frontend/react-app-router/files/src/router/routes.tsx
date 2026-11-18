/**
 * The route table of the app: one place, declarative (react-router in data mode).
 * `guard` and `headerActions` come from outside (main.tsx): the router does not know the auth capability,
 * it only receives a component that decides whether `children` may render.
 */

import { Fragment, type ComponentType, type ReactNode } from 'react'
import { createBrowserRouter, createHashRouter, type RouteObject } from 'react-router'

import { HomeScreen } from '../screens/HomeScreen'
import { ErrorScreen } from './ErrorScreen'
import { Layout } from './Layout'
import { NotFoundScreen } from './NotFoundScreen'

export type Guard = ComponentType<{ children: ReactNode }>

export type AppRoutesOptions = {
  /** Wraps every screen under the layout (e.g. `RequireSession`). Default: no guard. */
  guard?: Guard
  /** Rendered at the right of the header (e.g. a sign-out button). */
  headerActions?: ReactNode
}

/** Paths as constants: links and tests never retype a string. */
export const PATHS = {
  home: '/',
  settings: '/settings',
} as const

export function appRoutes({ guard: Guard = Fragment, headerActions }: AppRoutesOptions = {}): RouteObject[] {
  return [
    {
      path: PATHS.home,
      element: (
        <Guard>
          <Layout actions={headerActions} />
        </Guard>
      ),
      errorElement: <ErrorScreen />,
      children: [
        { index: true, element: <HomeScreen /> },
        // Lazy screen: its own chunk, downloaded on first visit. Add yours the same way.
        { path: PATHS.settings, lazy: async () => ({ Component: (await import('../screens/SettingsScreen')).SettingsScreen }) },
        { path: '*', element: <NotFoundScreen /> },
      ],
    },
  ]
}

export type RouterKind = 'browser' | 'hash'

/**
 * `browser` = clean URLs; the server must answer index.html for every path (Vite does, so does any SPA host).
 * `hash` = `#/settings`; works on a static host with no fallback.
 */
export function createAppRouter(options: AppRoutesOptions & { kind?: RouterKind } = {}) {
  const create = options.kind === 'hash' ? createHashRouter : createBrowserRouter
  return create(appRoutes(options))
}
