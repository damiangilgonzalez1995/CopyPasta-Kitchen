import { expect, test } from '@playwright/test'

import { enter } from './helpers'

test('links, deep links and the 404 work with the browser history', async ({ page }) => {
  await enter(page)
  await page.getByRole('link', { name: 'Ajustes' }).click()
  await expect(page).toHaveURL(/\/settings$/)
  await expect(page.getByRole('heading', { name: 'Ajustes' })).toBeVisible()

  await page.goBack()
  await expect(page.getByRole('heading', { name: 'Hola, Demo User' })).toBeVisible()

  await page.goto('/settings') // deep link: the server answers index.html for every path
  await expect(page.getByRole('heading', { name: 'Ajustes' })).toBeVisible()

  await page.goto('/nope')
  await expect(page.getByRole('heading', { name: 'Página no encontrada' })).toBeVisible()
  await page.getByRole('link', { name: 'Volver al inicio' }).click()
  await expect(page.getByRole('heading', { name: 'Hola, Demo User' })).toBeVisible()
})

test('the login keeps the URL you asked for', async ({ page }) => {
  await enter(page, '/settings')
  await expect(page).toHaveURL(/\/settings$/)
  await expect(page.getByRole('heading', { name: 'Ajustes' })).toBeVisible()
})
