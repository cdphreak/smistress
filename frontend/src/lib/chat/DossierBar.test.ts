import { render, screen } from '@testing-library/svelte';
import { expect, test, vi } from 'vitest';

vi.mock('$lib/api/supervision', () => ({
  getSupervision: vi.fn(async () => ({ mode: 'full', notes: {} })),
  setMode: vi.fn(async () => ({ mode: 'full', notes: {} })),
  setNote: vi.fn(async () => ({ mode: 'full', notes: {} }))
}));
vi.mock('$lib/stores/dossier.svelte', () => ({ dossier: { refresh: vi.fn() } }));

import DossierBar from './DossierBar.svelte';

const data = {
  rank: 'adept',
  merit: 50,
  tokens: 3,
  disposition: {
    band: 'cool',
    line: 'cool · exacting — 2 recent misses',
    reason: '2 recent misses',
    standing: 30
  },
  active_task: { description: 'Posture drill', status: 'assigned', intensity: 40, discreetness: 'discreet' },
  debt: 0,
  chastity: { locked: false, ends_at: null, seconds_remaining: 0 },
  supervision_mode: 'discreet'
};

test('shows rank, disposition line, mode badge and task tags', () => {
  render(DossierBar, { data });
  expect(screen.getByText(/adept/i)).toBeInTheDocument();
  expect(screen.getByText(/cool · exacting/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /mode · discreet/i })).toBeInTheDocument(); // mode badge
  expect(screen.getByText(/intensity 40/i)).toBeInTheDocument();
});

test('renders nothing-fatal when data is null', () => {
  render(DossierBar, { data: null });
  expect(screen.getByText(/…|loading/i)).toBeInTheDocument();
});
