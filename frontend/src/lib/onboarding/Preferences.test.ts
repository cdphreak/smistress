import { render, screen } from '@testing-library/svelte';
import { expect, test, vi } from 'vitest';
import Preferences from './Preferences.svelte';

test('submits ceiling + aftercare', async () => {
  const onnext = vi.fn();
  render(Preferences, { onnext });
  screen.getByRole('button', { name: /next/i }).click();
  expect(onnext).toHaveBeenCalledOnce();
  const prefs = onnext.mock.calls[0][0];
  expect(prefs.intensity_ceiling).toBeGreaterThanOrEqual(0);
  expect(prefs).toHaveProperty('aftercare_prefs');
});
