import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import ProgressRail from './ProgressRail.svelte';

test('marks the current step', () => {
  render(ProgressRail, { total: 9, current: 3 });
  expect(screen.getByText('3 / 9')).toBeInTheDocument();
});
