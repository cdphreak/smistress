import { render, screen } from '@testing-library/svelte';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/safety', () => ({
  getSafety: vi.fn(async () => ({ is_halted: false, on_hiatus: false, consent_check_due: true })),
  setHiatus: vi.fn(async (_id, on) => ({ is_halted: false, on_hiatus: on, consent_check_due: true })),
  lowerLimit: vi.fn(async (_id, kink, rating) => ({ kink, rating })),
  consentCheck: vi.fn(async () => ({ is_halted: false, on_hiatus: false, consent_check_due: false })),
  deleteProfile: vi.fn(async () => null)
}));

import Page from './+page.svelte';
import { session } from '$lib/stores/session.svelte';

beforeEach(() => {
  session.setProfileId('p1');
});

test('shows well-being controls and toggles hiatus', async () => {
  const api = await import('$lib/api/safety');
  render(Page);
  const toggle = await screen.findByRole('button', { name: /pause training/i });
  toggle.click();
  await vi.waitFor(() => expect(api.setHiatus).toHaveBeenCalledWith('p1', true));
});

test('consent check-in surfaces when due', async () => {
  render(Page);
  expect(await screen.findByText(/check-in due/i)).toBeInTheDocument();
});
