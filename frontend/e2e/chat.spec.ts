import { expect, test } from '@playwright/test';
import { mockApi } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.addInitScript(() => localStorage.setItem('smistress.profileId', 'e2e-profile'));
});

test('chat home shows the dossier and exchanges a message', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText(/cool · exacting/)).toBeVisible();

  await page.getByPlaceholder(/say something/i).fill('what now?');
  await page.getByRole('button', { name: /send/i }).click();

  // exact match: the reply "Heard: what now?" also contains "what now?"
  await expect(page.getByText('what now?', { exact: true })).toBeVisible(); // optimistic user bubble
  await expect(page.getByText('Heard: what now?')).toBeVisible(); // her reply
});

test('typed safeword short-circuits to the stop sheet (no chat call)', async ({ page }) => {
  await page.goto('/');
  await page.getByPlaceholder(/say something/i).fill('red');
  await page.getByRole('button', { name: /send/i }).click();
  // the global StopSheet shows the calm receipt; no "Heard: red" bubble
  await expect(page.getByText(/stopping/i)).toBeVisible();
  await expect(page.getByText('Heard: red')).toHaveCount(0);
});
