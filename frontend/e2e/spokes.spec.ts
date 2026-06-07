import { expect, test } from '@playwright/test';
import { mockApi } from './fixtures';

// Seed a profile id in localStorage so the guard lets us into the spokes.
test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.addInitScript(() => localStorage.setItem('smistress.profileId', 'e2e-profile'));
});

test('profile spoke shows the assembled dossier', async ({ page }) => {
  await page.goto('/profile');
  await expect(page.getByText('Headmistress')).toBeVisible();
  await expect(page.getByText('Apex')).toBeVisible();
  await expect(page.getByText(/bondage/i)).toBeVisible();
});

test('character spoke reveals the edit form with 7 dials', async ({ page }) => {
  await page.goto('/character');
  await expect(page.getByRole('heading', { name: 'Headmistress' })).toBeVisible();
  await page.getByRole('button', { name: /edit/i }).click();
  await expect(page.getByRole('slider')).toHaveCount(7);
});
