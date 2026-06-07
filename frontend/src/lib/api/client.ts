export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(`API ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function parse(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export function makeClient(base = '', fetchFn: typeof fetch = fetch) {
  async function request(method: string, path: string, body?: unknown): Promise<unknown> {
    const res = await fetchFn(`${base}${path}`, {
      method,
      headers: body === undefined ? undefined : { 'content-type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    const data = await parse(res);
    if (!res.ok) {
      const detail =
        data && typeof data === 'object' && 'detail' in data
          ? (data as { detail: unknown }).detail
          : data;
      throw new ApiError(res.status, detail);
    }
    return data;
  }
  return {
    get: (p: string) => request('GET', p),
    post: (p: string, b?: unknown) => request('POST', p, b),
    put: (p: string, b?: unknown) => request('PUT', p, b)
  };
}

// Browser singleton: talks to the same-origin BFF proxy.
export const api = makeClient('');
