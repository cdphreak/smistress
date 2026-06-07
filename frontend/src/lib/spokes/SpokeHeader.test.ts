import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import SpokeHeader from './SpokeHeader.svelte';

test('renders the title and a home link', () => {
  render(SpokeHeader, { title: 'Sub Profile' });
  expect(screen.getByText('Sub Profile')).toBeInTheDocument();
  const home = screen.getByRole('link', { name: /home/i });
  expect(home).toHaveAttribute('href', '/');
});
