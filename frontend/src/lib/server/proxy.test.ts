import { describe, expect, test, vi } from 'vitest';
import { proxyRequest } from './proxy';

describe('proxyRequest', () => {
  test('forwards method + path + body to the API origin and returns the upstream response', async () => {
    const fetchFn = vi.fn<typeof fetch>(async () =>
      new Response(JSON.stringify({ ok: true }), { status: 201, headers: { 'content-type': 'application/json' } })
    );
    const req = new Request('http://localhost/api/onboarding/profile', {
      method: 'POST', body: JSON.stringify({ is_adult: true }), headers: { 'content-type': 'application/json' }
    });
    const res = await proxyRequest(req, 'onboarding/profile', 'http://api:8000', fetchFn);
    expect(res.status).toBe(201);
    const [calledUrl, init] = fetchFn.mock.calls[0];
    expect(calledUrl).toBe('http://api:8000/onboarding/profile');
    expect(init?.method).toBe('POST');
  });

  test('preserves query string', async () => {
    const fetchFn = vi.fn<typeof fetch>(async () => new Response('{}', { status: 200 }));
    const req = new Request('http://localhost/api/profile/x/disposition?q=1');
    await proxyRequest(req, 'profile/x/disposition', 'http://api:8000', fetchFn);
    expect(fetchFn.mock.calls[0][0]).toBe('http://api:8000/profile/x/disposition?q=1');
  });
});
