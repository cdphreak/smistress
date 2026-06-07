import { render, screen } from '@testing-library/svelte';
import { expect, test, vi } from 'vitest';
import SegmentedControl from './SegmentedControl.svelte';

test('selects an option and reports the value', async () => {
  const onchange = vi.fn();
  render(SegmentedControl, {
    options: [
      { value: 'a', label: 'A' },
      { value: 'b', label: 'B' }
    ],
    value: 'a',
    onchange
  });
  screen.getByRole('button', { name: 'B' }).click();
  expect(onchange).toHaveBeenCalledWith('b');
});
