/** Shared steps. Plain functions, not page objects: a spec reads top to bottom. */

import { expect, type Page } from '@playwright/test'

/** The account of the fake auth (src/auth/fake-auth.ts). */
export const DEMO = { email: 'demo@example.com', password: 'demo' }

/** Opens `path` and signs in with the fake account. */
export async function enter(page: Page, path = '/') {
  await page.goto(path)
  await page.getByLabel('Correo').fill(DEMO.email)
  await page.getByLabel('Contraseña').fill(DEMO.password)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page.getByRole('heading', { name: 'Entrar' })).toBeHidden()
}

/** Fails the test on any console error (a React warning, an unhandled rejection). */
export function failOnConsoleErrors(page: Page) {
  const errors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  page.on('pageerror', (error) => errors.push(error.message))
  return () => expect(errors, 'console errors').toEqual([])
}
