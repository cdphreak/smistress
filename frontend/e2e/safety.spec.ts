import { expect, test } from '@playwright/test';
import { mockApi } from './fixtures';

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.addInitScript(() => localStorage.setItem('smistress.profileId', 'e2e-profile'));
});

test('SAFE button pre-halts, confirm shows the calm receipt', async ({ page }) => {
  await page.goto('/profile');
  // The SAFE button's accessible name is the full aria-label "SAFE — stop everything".
  // getByRole with the exact text "SAFE" would not match; target by the full aria-label.
  await page.getByRole('button', { name: 'SAFE — stop everything' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  // Scope the confirm button to the dialog: the fixed SAFE button's accessible
  // name ("SAFE — stop everything") also contains "stop everything", so an
  // unscoped match would be ambiguous (strict-mode violation).
  const confirm = dialog.getByRole('button', { name: /^stop everything$/i });
  await expect(confirm).toBeVisible();

  await confirm.click();
  await expect(page.getByText(/stopping now/i)).toBeVisible();
  await expect(page.getByText(/rest a while/i)).toBeVisible();
});
