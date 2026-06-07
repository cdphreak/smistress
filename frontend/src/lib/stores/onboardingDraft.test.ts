import { beforeEach, expect, test } from 'vitest';
import { onboardingDraft } from './onboardingDraft.svelte';

beforeEach(() => localStorage.clear());

test('persists and reloads draft answers', () => {
  onboardingDraft.set('archetype', { q1: 4 });
  expect(onboardingDraft.get('archetype')).toEqual({ q1: 4 });
  // a fresh read reflects what was written (localStorage-backed)
  expect(JSON.parse(localStorage.getItem('smistress.onboarding') ?? '{}').archetype).toEqual({
    q1: 4
  });
});

test('clear wipes the draft', () => {
  onboardingDraft.set('toys', [{ name: 'x', type: 'y' }]);
  onboardingDraft.clear();
  expect(onboardingDraft.get('toys')).toBeUndefined();
});
