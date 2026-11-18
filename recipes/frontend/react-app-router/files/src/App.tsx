import { RouterProvider, type createBrowserRouter } from 'react-router'

import { AppProvider, type AppServices } from './app-context'

export type AppRouter = ReturnType<typeof createBrowserRouter>

/** Root component. Gets its services and its router from outside (main.tsx or a test), so it never builds them. */
export function App({ services, router }: { services: AppServices; router: AppRouter }) {
  return (
    <AppProvider services={services}>
      <RouterProvider router={router} />
    </AppProvider>
  )
}
