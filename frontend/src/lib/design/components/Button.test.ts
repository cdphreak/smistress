import { render, screen } from '@testing-library/svelte';
import { expect, test, vi } from 'vitest';
import Button from './Button.svelte';

test('renders label and fires onclick', async () => {
  const onclick = vi.fn();
  render(Button, { label: 'NEXT', onclick });
  const btn = screen.getByRole('button', { name: 'NEXT' });
  btn.click();
  expect(onclick).toHaveBeenCalledOnce();
});

test('disabled button does not fire', async () => {
  const onclick = vi.fn();
  render(Button, { label: 'NEXT', onclick, disabled: true });
  screen.getByRole('button').click();
  expect(onclick).not.toHaveBeenCalled();
});
