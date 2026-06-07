import { expect, test } from '@playwright/test';
import { mockApi } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.addInitScript(() => localStorage.setItem('smistress.profileId', 'e2e-profile'));
});

test('an assign_task reply renders an inline action card', async ({ page }) => {
  await page.goto('/');
  await page.getByPlaceholder(/say something/i).fill('give me a task');
  await page.getByRole('button', { name: /send/i }).click();

  await expect(page.getByText('Heard: give me a task')).toBeVisible(); // her bubble
  await expect(page.getByText(/task assigned/i)).toBeVisible(); // the card
  await expect(page.getByText(/Posture drill/)).toBeVisible();
});
