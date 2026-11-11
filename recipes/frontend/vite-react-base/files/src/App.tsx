import { AppProvider, type AppServices } from './app-context'
import { HomeScreen } from './screens/HomeScreen'

/** Root component. Gets its services from outside (main.tsx or a test), so it never builds an Api itself. */
export function App({ services }: { services: AppServices }) {
  return (
    <AppProvider services={services}>
      <main className="layout">
        <HomeScreen />
      </main>
    </AppProvider>
  )
}
