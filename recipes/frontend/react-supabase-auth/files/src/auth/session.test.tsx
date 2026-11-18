import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { createFakeAuth } from './fake-auth'
import { RequireSession, SessionProvider } from './session-context'
import { createSessionStore } from './session-store'

function mount(store = createSessionStore(createFakeAuth({ latencyMs: 0 }))) {
  render(
    <SessionProvider store={store}>
      <RequireSession>
        <h1>Dentro</h1>
      </RequireSession>
    </SessionProvider>,
  )
  return store
}

async function enter(email = 'demo@example.com', password = 'demo') {
  await userEvent.type(await screen.findByLabelText('Correo'), email)
  await userEvent.type(screen.getByLabelText('Contraseña'), password)
  await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
}

describe('RequireSession', () => {
  it('shows the login, then the content after signing in', async () => {
    mount()
    expect(await screen.findByRole('heading', { name: 'Entrar' })).toBeTruthy()
    await enter()
    expect(await screen.findByRole('heading', { name: 'Dentro' })).toBeTruthy()
  })

  it('shows a message by code and keeps the form on a wrong password', async () => {
    mount()
    await enter('demo@example.com', 'wrong')
    expect((await screen.findByRole('alert')).textContent).toContain('No coinciden')
    expect(screen.getByRole('button', { name: 'Entrar' })).toBeTruthy()
  })

  it('skips the login when a session is stored', async () => {
    const auth = createFakeAuth({ latencyMs: 0 })
    await auth.signIn({ email: 'demo@example.com', password: 'demo' })
    mount(createSessionStore(auth))
    expect(await screen.findByRole('heading', { name: 'Dentro' })).toBeTruthy()
  })

  it('goes back to the login and says why when the session expires', async () => {
    const store = mount()
    await enter()
    await screen.findByRole('heading', { name: 'Dentro' })
    store.expire()
    expect(await screen.findByRole('heading', { name: 'Entrar' })).toBeTruthy()
    expect(screen.getByText('Tu sesión ha caducado')).toBeTruthy()
  })
})
