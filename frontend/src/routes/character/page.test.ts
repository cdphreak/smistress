import { render, screen } from '@testing-library/svelte';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/profile', () => ({
  getCharacter: vi.fn(async () => ({
    name: null,
    honorific: 'Headmistress',
    address_term: 'student',
    pronouns: 'she/her',
    archetype_blend: { governess: 70, drill_instructor: 30 },
    warmth: 40, strictness: 80, sadism: 30, formality: 70,
    verbosity: 50, crudeness: 30, wit: 75, signature_flavor: null
  })),
  putCharacter: vi.fn(async () => ({}))
}));

import Page from './+page.svelte';
import { session } from '$lib/stores/session.svelte';

beforeEach(() => session.setProfileId('p1'));

test('shows current character then reveals the edit form', async () => {
  render(Page);
  expect(await screen.findByText('Headmistress')).toBeInTheDocument();
  screen.getByRole('button', { name: /edit/i }).click();
  // edit form seeds the honorific field with the current value
  const sliders = await screen.findAllByRole('slider');
  expect(sliders.length).toBe(7); // 7 voice dials
});
