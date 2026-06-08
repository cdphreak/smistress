import { expect, test } from '@playwright/test';
import { mockApi } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.addInitScript(() => localStorage.setItem('smistress.profileId', 'e2e-profile'));
});

test('offline: home shows drone standing orders, not the chat composer', async ({ page }) => {
  // Override availability to offline (registered after mockApi -> takes precedence).
  await page.route('**/api/llm/availability', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ state: 'offline', online: false, last_heartbeat_at: null })
    })
  );
  await page.route('**/standing-orders', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        notices: [
          { unit: 'assignment', line: 'Mistress has assigned: Posture drill. Report when complete.' },
          { unit: 'reminder', line: 'Denial remains in effect. Endure it until she lifts it.' }
        ]
      })
    })
  );

  await page.goto('/');
  await expect(page.getByText(/her drones hold your standing orders/i)).toBeVisible();
  await expect(page.getByText('Mistress has assigned: Posture drill. Report when complete.')).toBeVisible();
  await expect(page.getByText(/an audience requires her presence/i)).toBeVisible();
  // no live composer when she is away
  await expect(page.getByPlaceholder(/say something/i)).toHaveCount(0);
});

test('online: home still shows the live chat composer', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByPlaceholder(/say something/i)).toBeVisible();
});
