/// <reference types="@testing-library/jest-dom/vitest" />
import { render, screen } from '@testing-library/svelte';
import { expect, test } from 'vitest';
import Hello from './design/components/Hello.svelte';

test('renders a svelte component under jsdom', () => {
  render(Hello, { name: 'student' });
  expect(screen.getByText('hello student')).toBeInTheDocument();
});
