import { render, screen } from '@testing-library/svelte';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/supervision', () => ({
  getSupervision: vi.fn(async () => ({ mode: 'full', notes: {} })),
  setMode: vi.fn(async (_id: string, mode: string) => ({ mode, notes: {} })),
  setNote: vi.fn(async () => ({ mode: 'full', notes: {} }))
}));
vi.mock('$lib/stores/dossier.svelte', () => ({
  dossier: { refresh: vi.fn(async () => {}) }
}));

import ModeSheet from './ModeSheet.svelte';
import { supervision } from '$lib/stores/supervision.svelte';
import { setMode } from '$lib/api/supervision';
import { session } from '$lib/stores/session.svelte';

beforeEach(() => {
  vi.clearAllMocks();
  session.setProfileId('p1');
  supervision.mode = 'full';
  supervision.notes = {};
});

test('renders nothing when closed', () => {
  render(ModeSheet, { open: false, onclose: () => {} });
  expect(screen.queryByText(/supervision/i)).not.toBeInTheDocument();
});

test('lists all modes and switches on click', async () => {
  render(ModeSheet, { open: true, onclose: () => {} });
  expect(screen.getByRole('button', { name: /discreet/i })).toBeInTheDocument();
  screen.getByRole('button', { name: /homeoffice/i }).click();
  await vi.waitFor(() => expect(setMode).toHaveBeenCalledWith('p1', 'homeoffice'));
});
