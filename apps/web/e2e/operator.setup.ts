import { expect, test as setup } from '@playwright/test';
import { OPERATOR, OPERATOR_STATE } from './operator';

setup('first run: create the operator account through the UI', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Create the operator account' })).toBeVisible();

  await page.getByLabel('Email').fill(OPERATOR.email);
  await page.getByLabel('Password').fill('short');
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page.getByRole('alert')).toContainText('at least 10 characters');

  await page.getByLabel('Password').fill(OPERATOR.password);
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page.getByRole('heading', { name: 'No missions yet' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();

  await page.context().storageState({ path: OPERATOR_STATE });
});
