import { expect, test } from '@playwright/test'

import { DEMO, enter } from './helpers'

test('a wrong password shows a message and the right one gets in', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Correo').fill(DEMO.email)
  await page.getByLabel('Contraseña').fill('wrong')
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page.getByRole('alert')).toHaveText('No coinciden el correo y la contraseña')

  await page.getByLabel('Contraseña').fill(DEMO.password)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page.getByRole('heading', { name: 'Hola, Demo User' })).toBeVisible()
})

test('the session survives a reload and signing out ends it', async ({ page }) => {
  await enter(page)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Hola, Demo User' })).toBeVisible()

  await page.getByRole('button', { name: /^Salir/ }).click()
  await expect(page.getByRole('heading', { name: 'Entrar' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Entrar' })).toBeVisible()
})
