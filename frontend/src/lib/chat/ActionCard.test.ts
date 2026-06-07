import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import ActionCard from './ActionCard.svelte';

test('renders an assign_task card', () => {
  render(ActionCard, {
    action: { tool: 'assign_task', description: 'Posture drill', proof: 'honor', merit_reward: 10 }
  });
  expect(screen.getByText(/task assigned/i)).toBeInTheDocument();
  expect(screen.getByText(/Posture drill/)).toBeInTheDocument();
  expect(screen.getByText(/honor/)).toBeInTheDocument();
});

test('renders a grant_tokens card', () => {
  render(ActionCard, { action: { tool: 'grant_tokens', amount: 2 } });
  expect(screen.getByText(/\+2 tokens/i)).toBeInTheDocument();
});

test('renders an error card', () => {
  render(ActionCard, { action: { tool: 'grant_tokens', error: 'amount must be >= 1' } });
  expect(screen.getByText(/couldn’t|error/i)).toBeInTheDocument();
});
