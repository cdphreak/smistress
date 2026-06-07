import { render, screen } from '@testing-library/svelte';
import { expect, test, vi } from 'vitest';
import Archetype from './Archetype.svelte';

const statements = [
  { id: 'q1', archetype: 'submissive', text: 'A' },
  { id: 'q2', archetype: 'slave', text: 'B' }
];

test('renders a scale per statement and submits the answers map', async () => {
  const onnext = vi.fn();
  render(Archetype, { statements, scale: { min: 0, max: 4 }, onnext });
  expect(screen.getAllByRole('slider')).toHaveLength(2);
  screen.getByRole('button', { name: /next/i }).click();
  expect(onnext).toHaveBeenCalledOnce();
  const answers = onnext.mock.calls[0][0];
  expect(Object.keys(answers)).toEqual(['q1', 'q2']);
});
