import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import Reveal from './Reveal.svelte';

test('shows the mistress honorific from the assembled profile', () => {
  render(Reveal, { character: { honorific: 'Headmistress', address_term: 'student' } });
  expect(screen.getByText(/Headmistress/)).toBeInTheDocument();
});
