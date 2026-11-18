/** Route error boundary: a screen that throws while rendering shows this instead of a blank page. */

import { isRouteErrorResponse, useRouteError } from 'react-router'

export function ErrorScreen() {
  const error = useRouteError()
  const title = isRouteErrorResponse(error) ? `Error ${error.status}` : 'Algo ha fallado'
  // Only the class reaches the screen; the message may carry internals.
  const kind = error instanceof Error ? error.name : typeof error
  return (
    <main className="layout">
      <section role="alert" className="card">
        <h1>{title}</h1>
        <p className="muted">{kind}</p>
        <button className="button" onClick={() => window.location.reload()}>
          Recargar
        </button>
      </section>
    </main>
  )
}
