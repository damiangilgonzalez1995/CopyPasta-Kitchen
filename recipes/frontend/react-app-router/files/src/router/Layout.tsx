/** Shell of every screen: header with navigation and the current screen in `<Outlet>`. */

import type { ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router'

import { CONFIG } from '../config'
import { PATHS } from './routes'
import './router.css'

export function Layout({ actions }: { actions?: ReactNode }) {
  return (
    <>
      <header className="topbar">
        <strong className="topbar-brand">{CONFIG.appName}</strong>
        <nav className="topbar-nav" aria-label="Principal">
          <NavLink to={PATHS.home} end>
            Inicio
          </NavLink>
          <NavLink to={PATHS.settings}>Ajustes</NavLink>
        </nav>
        {actions && <div className="topbar-actions">{actions}</div>}
      </header>
      <main className="layout">
        <Outlet />
      </main>
    </>
  )
}
