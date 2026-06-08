import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/availability', () => ({
  getAvailability: vi.fn()
}));

import { getAvailability } from '$lib/api/availability';
import { availability } from './availability.svelte';

beforeEach(() => {
  availability.online = false;
  vi.clearAllMocks();
});

test('refresh sets online from the api', async () => {
  (getAvailability as ReturnType<typeof vi.fn>).mockResolvedValue({
    state: 'online',
    online: true,
    last_heartbeat_at: 'now'
  });
  await availability.refresh();
  expect(availability.online).toBe(true);
});

test('refresh treats an api error as offline', async () => {
  (getAvailability as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('boom'));
  availability.online = true;
  await availability.refresh();
  expect(availability.online).toBe(false);
});

test('setOffline flips online to false', () => {
  availability.online = true;
  availability.setOffline();
  expect(availability.online).toBe(false);
});
