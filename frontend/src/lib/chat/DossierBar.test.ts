import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
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
  active_task: { description: 'Posture drill', status: 'assigned' },
  debt: 0,
  chastity: { locked: false, ends_at: null, seconds_remaining: 0 }
};

test('shows rank, merit and the disposition line', () => {
  render(DossierBar, { data });
  expect(screen.getByText(/adept/i)).toBeInTheDocument();
  expect(screen.getByText(/cool · exacting/)).toBeInTheDocument();
});

test('renders nothing-fatal when data is null', () => {
  render(DossierBar, { data: null });
  expect(screen.getByText(/…|loading/i)).toBeInTheDocument();
});
