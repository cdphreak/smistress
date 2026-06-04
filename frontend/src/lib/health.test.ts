import { describe, it, expect, vi } from 'vitest';
import { fetchHealth } from './health';

describe('fetchHealth', () => {
  it('returns parsed health json', async () => {
    const mockFetch = vi.fn(async () =>
      new Response(JSON.stringify({ status: 'ok', vision_enabled: false }), { status: 200 })
    );
    const result = await fetchHealth('http://api', mockFetch as unknown as typeof fetch);
    expect(result.status).toBe('ok');
    expect(result.vision_enabled).toBe(false);
  });
});
