export interface Health {
  status: string;
  vision_enabled: boolean;
}

export async function fetchHealth(
  apiBase: string,
  fetchFn: typeof fetch = fetch
): Promise<Health> {
  const res = await fetchFn(`${apiBase}/health`);
  if (!res.ok) throw new Error(`health check failed: ${res.status}`);
  return (await res.json()) as Health;
}
