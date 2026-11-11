import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { App } from './App'
import { ApiError, NetworkError, type Api } from './api/api'
import { createFakeApi } from './api/fake/fake-api'
import { makeApi } from './api/make-api'

describe('App with the fake api', () => {
  it('renders data loaded through the context', async () => {
    render(<App services={{ api: createFakeApi({ latencyMs: 0 }) }} />)

    expect(await screen.findByRole('heading', { name: 'Hola, Demo User' })).toBeTruthy()
  })

  it('shows an error by code and retries', async () => {
    let calls = 0
    const api: Api = {
      ...createFakeApi({ latencyMs: 0 }),
      me: async () => {
        calls += 1
        if (calls === 1) throw new ApiError(403, 'forbidden')
        return { userId: 'u', tenantId: 't', name: 'Ana' }
      },
    }
    render(<App services={{ api }} />)

    expect((await screen.findByRole('alert')).textContent).toContain('forbidden')
    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('heading', { name: 'Hola, Ana' })).toBeTruthy()
  })

  it('tells offline apart from an API error', async () => {
    const api: Api = { me: async () => Promise.reject(new NetworkError()) }
    render(<App services={{ api }} />)
    expect((await screen.findByRole('alert')).textContent).toContain('Sin conexión')
  })
})

describe('makeApi factory', () => {
  it('builds the implementation the settings name', async () => {
    const fake = await makeApi({ mode: 'fake', apiUrl: '/api' })
    expect(await fake.me()).toMatchObject({ name: 'Demo User' })

    const http = await makeApi({ mode: 'http', apiUrl: '/api' })
    expect(typeof http.me).toBe('function')
  })
})
