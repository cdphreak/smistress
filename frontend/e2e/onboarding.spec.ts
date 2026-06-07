import { expect, test } from '@playwright/test';
import { mockApi } from './fixtures';

test('consent gate creates a profile and advances the wizard', async ({ page }) => {
  await mockApi(page);
  await page.goto('/onboarding/consent');

  await expect(page.getByRole('heading', { name: /the frame/i })).toBeVisible();
  // Begin is gated (disabled) until both boxes are checked.
  await expect(page.getByRole('button', { name: /begin/i })).toBeDisabled();

  await page.getByLabel(/18 or older/i).check();
  await page.getByLabel(/i consent/i).check();
  await expect(page.getByRole('button', { name: /begin/i })).toBeEnabled();
  await page.getByRole('button', { name: /begin/i }).click();

  // advances to the archetype step (questionnaire renders scales)
  await expect(page).toHaveURL(/\/onboarding\/archetype/);
  await expect(page.getByRole('slider').first()).toBeVisible();
});
