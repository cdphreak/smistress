<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchHealth, type Health } from '$lib/health';

  let health: Health | null = $state(null);
  let error: string | null = $state(null);
  const apiBase = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

  onMount(async () => {
    try {
      health = await fetchHealth(apiBase);
    } catch (e) {
      error = (e as Error).message;
    }
  });
</script>

<h1>smistress</h1>
{#if error}<p>backend unreachable: {error}</p>
{:else if health}<p>backend: {health.status}</p>
{:else}<p>connecting…</p>{/if}
