import { expect, test } from '@playwright/test'

import { enter, failOnConsoleErrors } from './helpers'

test('the home shows the data of the fake api', async ({ page }) => {
  const check = failOnConsoleErrors(page)
  await enter(page)
  await expect(page.getByRole('heading', { name: 'Hola, Demo User' })).toBeVisible()
  check()
})
