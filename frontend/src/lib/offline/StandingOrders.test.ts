import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';

import StandingOrders from './StandingOrders.svelte';

test('renders the away header and each drone notice', () => {
  render(StandingOrders, {
    notices: [
      { unit: 'assignment', line: 'Mistress has assigned: Posture drill. Report when complete.' },
      { unit: 'reminder', line: 'Denial remains in effect. Endure it until she lifts it.' }
    ]
  });
  expect(screen.getByText(/she is away/i)).toBeInTheDocument();
  expect(screen.getByText(/Posture drill/)).toBeInTheDocument();
  expect(screen.getByText(/Denial remains in effect/)).toBeInTheDocument();
  // unit labels are surfaced
  expect(screen.getByText('assignment')).toBeInTheDocument();
  expect(screen.getByText('reminder')).toBeInTheDocument();
});
