import { render, screen } from '@testing-library/svelte';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/profile', () => ({
  getProfile: vi.fn(async () => ({
    id: 'p1',
    intensity_ceiling: 60,
    aftercare_prefs: 'tea',
    archetype_scores: { submissive: 80, slave: 20 },
    kinks: [{ kink: 'bondage', rating: 'favorite' }],
    toys: [{ name: 'Apex', type: 'vibrator' }],
    goals: [{ title: 'Posture', description: '', status: 'active' }],
    so_context: { description: 'partner', values: null, dynamic: null },
    character: { honorific: 'Headmistress', address_term: 'student' }
  })),
  putKinks: vi.fn(),
  addToy: vi.fn(),
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
