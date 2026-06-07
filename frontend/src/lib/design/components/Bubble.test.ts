import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import Bubble from './Bubble.svelte';

test('renders content and tags the speaker', () => {
  const { container } = render(Bubble, { role: 'assistant', content: 'Kneel.' });
  expect(screen.getByText('Kneel.')).toBeInTheDocument();
  expect(container.querySelector('.bubble.mistress')).not.toBeNull();
});

test('the sub bubble is right-aligned', () => {
  const { container } = render(Bubble, { role: 'user', content: 'yes' });
  expect(container.querySelector('.bubble.sub')).not.toBeNull();
});
