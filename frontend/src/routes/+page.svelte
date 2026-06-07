<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores/session.svelte';
  onMount(() => {
    if (!session.profileId) goto('/onboarding/consent');
  });
</script>

<p>…</p>
