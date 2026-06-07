import { beforeEach, expect, test } from 'vitest';
import { session } from './session.svelte';

beforeEach(() => localStorage.clear());

test('stores and clears the profile id', () => {
  session.setProfileId('abc');
  expect(session.profileId).toBe('abc');
  session.clear();
  expect(session.profileId).toBeNull();
});
