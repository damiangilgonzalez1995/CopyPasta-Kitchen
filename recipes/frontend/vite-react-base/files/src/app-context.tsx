/**
 * App services reach components through context, never through imports of singletons:
 * tests render the same components with a fake `Api`.
 */

import { createContext, useContext, type ReactNode } from 'react'

import type { Api } from './api/api'

export type AppServices = {
  api: Api
}

const AppContext = createContext<AppServices | null>(null)

export function AppProvider({ services, children }: { services: AppServices; children: ReactNode }) {
  return <AppContext.Provider value={services}>{children}</AppContext.Provider>
}

export function useApp(): AppServices {
  const services = useContext(AppContext)
  if (!services) throw new Error('useApp() outside <AppProvider>')
  return services
}
