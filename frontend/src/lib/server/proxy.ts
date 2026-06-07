// Pure proxy core (testable without SvelteKit). Forwards a request to the API origin.
export async function proxyRequest(
  request: Request,
  path: string,
  apiOrigin: string,
  fetchFn: typeof fetch = fetch
): Promise<Response> {
  const incoming = new URL(request.url);
  const target = `${apiOrigin}/${path}${incoming.search}`;
  const headers = new Headers(request.headers);
  headers.delete('host');
  const method = request.method;
  const body = method === 'GET' || method === 'HEAD' ? undefined : await request.arrayBuffer();
  const upstream = await fetchFn(target, {
    method,
    headers,
    body,
    redirect: 'manual'
  });
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: upstream.headers
  });
}
