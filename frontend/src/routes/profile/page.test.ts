import { render, screen, within, fireEvent } from '@testing-library/svelte';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/profile', () => ({
  getProfile: vi.fn(async () => ({
    id: 'p1',
    intensity_ceiling: 60,
    aftercare_prefs: 'tea',
    archetype_scores: { submissive: 80, slave: 20 },
    kinks: [{ kink: 'bondage', rating: 'favorite' }],
    toys: [{ id: 't1', name: 'Apex', type: 'vibrator', noise: false, visibility: false, discreet_capable: true, intiface_capable: false }],
    goals: [{ title: 'Posture', description: '', status: 'active' }],
    so_context: { description: 'partner', values: null, dynamic: null },
    character: { honorific: 'Headmistress', address_term: 'student' }
  })),
  putKinks: vi.fn(),
  addToy: vi.fn(),
  updateToy: vi.fn(),
  addGoal: vi.fn(),
  putSoContext: vi.fn(),
  putPreferences: vi.fn()
}));
vi.mock('$lib/api/onboarding', () => ({
  getQuestionnaire: vi.fn(async () => ({
    statements: [],
    kinks: ['bondage', 'spanking'],
    toy_types: ['vibrator', 'chastity_cage'],
    answer_scale: { min: 0, max: 4 }
  }))
}));

import Page from './+page.svelte';
import { session } from '$lib/stores/session.svelte';

beforeEach(() => session.setProfileId('p1'));

test('renders the assembled profile after load', async () => {
  render(Page);
  expect(await screen.findByText('Headmistress')).toBeInTheDocument();
  expect(screen.getByText(/submissive/i)).toBeInTheDocument();
  expect(screen.getByText('Apex')).toBeInTheDocument();
});

test('shows toy discreetness flags', async () => {
  render(Page);
  expect(await screen.findByText('Apex')).toBeInTheDocument();
  expect(screen.getByText(/discreet/i)).toBeInTheDocument();
});

test('editing a toy calls updateToy, not addToy', async () => {
  const { updateToy, addToy } = await import('$lib/api/profile');
  render(Page);
  // wait for the toy list to render
  const apexEl = await screen.findByText('Apex');
  // scope to the <li> containing the Apex toy to avoid ambiguous Edit buttons
  const toyLi = apexEl.closest('li')!;
  // open the per-toy edit form
  await fireEvent.click(within(toyLi).getByRole('button', { name: /edit/i }));
  // the Toys edit form shows a "Save" button (edit mode) prefilled from the toy
  const save = await screen.findByRole('button', { name: /save/i });
  await fireEvent.click(save);
  await vi.waitFor(() => expect(updateToy).toHaveBeenCalled());
  expect(addToy).not.toHaveBeenCalled();
  // it should target the edited toy's id ('t1' in the fixture)
  expect((updateToy as any).mock.calls[0][1]).toBe('t1');
});
