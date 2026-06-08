import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/drones', () => ({
  getStandingOrders: vi.fn()
}));

import { getStandingOrders } from '$lib/api/drones';
import { drones } from './drones.svelte';
import { session } from './session.svelte';

beforeEach(() => {
  drones.notices = [];
  session.setProfileId('p1');
  vi.clearAllMocks();
});

test('refresh loads notices for the current profile', async () => {
  (getStandingOrders as ReturnType<typeof vi.fn>).mockResolvedValue({
    notices: [{ unit: 'assignment', line: 'No standing assignment.' }]
  });
  await drones.refresh();
  expect(drones.notices).toEqual([{ unit: 'assignment', line: 'No standing assignment.' }]);
});

test('refresh is a no-op without a profile', async () => {
  session.setProfileId('');
  await drones.refresh();
  expect(getStandingOrders).not.toHaveBeenCalled();
});
