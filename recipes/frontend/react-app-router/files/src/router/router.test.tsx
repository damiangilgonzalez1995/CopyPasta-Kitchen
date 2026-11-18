import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { createMemoryRouter, RouterProvider, type RouteObject } from 'react-router'
import { describe, expect, it } from 'vitest'

import { createFakeApi } from '../api/fake/fake-api'
import { AppProvider } from '../app-context'
import { appRoutes, PATHS, type AppRoutesOptions } from './routes'

function mount(path: string, options: AppRoutesOptions = {}) {
  const router = createMemoryRouter(appRoutes(options), { initialEntries: [path] })
  render(
    <AppProvider services={{ api: createFakeApi({ latencyMs: 0 }) }}>
      <RouterProvider router={router} />
    </AppProvider>,
  )
  return router
}

describe('app routes', () => {
  it('renders the home under the layout and navigates with the links', async () => {
    const router = mount(PATHS.home)
    expect(await screen.findByRole('heading', { name: 'Hola, Demo User' })).toBeTruthy()
    await userEvent.click(screen.getByRole('link', { name: 'Ajustes' }))
    expect(await screen.findByRole('heading', { name: 'Ajustes' })).toBeTruthy()
    expect(router.state.location.pathname).toBe(PATHS.settings)
    expect(screen.getByRole('link', { name: 'Ajustes' }).className).toContain('active')
  })

  it('loads a lazy screen by URL', async () => {
    mount(PATHS.settings)
    expect(await screen.findByRole('heading', { name: 'Ajustes' })).toBeTruthy()
  })

  it('shows a 404 with a way back', async () => {
    mount('/nope')
    expect(await screen.findByRole('heading', { name: 'Página no encontrada' })).toBeTruthy()
    await userEvent.click(screen.getByRole('link', { name: 'Volver al inicio' }))
    expect(await screen.findByRole('heading', { name: 'Hola, Demo User' })).toBeTruthy()
  })

  it('runs every screen through the guard and renders the header actions', async () => {
    const Guard = ({ children }: { children: ReactNode }) => <div data-testid="guarded">{children}</div>
    mount(PATHS.settings, { guard: Guard, headerActions: <button>Salir</button> })
    expect(await screen.findByRole('heading', { name: 'Ajustes' })).toBeTruthy()
    expect(screen.getByTestId('guarded')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Salir' })).toBeTruthy()
  })

  it('a screen that throws shows the error screen with only the error class', async () => {
    const Boom = () => {
      throw new Error('secret internals')
    }
    const [root] = appRoutes()
    const router = createMemoryRouter([{ ...root, index: undefined, children: [{ index: true, element: <Boom /> }] } as RouteObject], {
      initialEntries: [PATHS.home],
    })
    render(<RouterProvider router={router} />)
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('Algo ha fallado')
    expect(alert.textContent).toContain('Error')
    expect(alert.textContent).not.toContain('secret internals')
  })
})
