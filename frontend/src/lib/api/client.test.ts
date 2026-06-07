import { describe, expect, test, vi } from 'vitest';
import { ApiError, makeClient } from './client';

describe('api client', () => {
  test('GET returns parsed JSON', async () => {
    const fetchFn = vi.fn(async () => new Response(JSON.stringify({ a: 1 }), { status: 200 }));
    const api = makeClient('', fetchFn);
    expect(await api.get('/api/x')).toEqual({ a: 1 });
  });

  test('non-2xx throws ApiError with status + detail', async () => {
    const fetchFn = vi.fn(
      async () => new Response(JSON.stringify({ detail: 'nope' }), { status: 422 })
    );
    const api = makeClient('', fetchFn);
    await expect(api.post('/api/x', { y: 1 })).rejects.toMatchObject({
      status: 422,
      detail: 'nope'
    });
    expect(ApiError).toBeTruthy();
  });
});
