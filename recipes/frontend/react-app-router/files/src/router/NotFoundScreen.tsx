import { Link } from 'react-router'

import { PATHS } from './routes'

export function NotFoundScreen() {
  return (
    <section className="card">
      <h1>Página no encontrada</h1>
      <Link to={PATHS.home}>Volver al inicio</Link>
    </section>
  )
}
