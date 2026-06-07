import { describe, expect, test, vi } from 'vitest';
import { makeClient } from './client';

describe('client.del', () => {
  test('issues a DELETE and returns parsed body (or null on empty)', async () => {
    const fetchFn = vi.fn(async () => new Response('', { status: 200 }));
    const api = makeClient('', fetchFn);
    expect(await api.del('/api/profile/x')).toBeNull();
    const [, init] = fetchFn.mock.calls[0] as unknown as [unknown, RequestInit?];
    expect(init?.method).toBe('DELETE');
  });
});
