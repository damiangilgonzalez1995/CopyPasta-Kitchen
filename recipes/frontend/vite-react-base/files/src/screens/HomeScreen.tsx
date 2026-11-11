/** Example screen: loads data through `useApp().api` and shows the three states. Replace it with yours. */

import { ApiError } from '../api/api'
import { useApp } from '../app-context'
import { useLoad } from '../hooks/use-load'

export function HomeScreen() {
  const { api } = useApp()
  const { data, loading, error, reload } = useLoad(() => api.me(), [api])

  if (loading) return <p className="muted">Cargando…</p>
  if (error) {
    const message = error instanceof ApiError ? `Error ${error.code}` : 'Sin conexión con el servidor'
    return (
      <div role="alert" className="card">
        <p>{message}</p>
        <button className="button" onClick={reload}>
          Reintentar
        </button>
      </div>
    )
  }
  return (
    <section className="card">
      <h1>Hola, {data?.name}</h1>
    </section>
  )
}
