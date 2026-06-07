<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores/session.svelte';

  onMount(() => {
    if (!session.profileId) goto('/onboarding/consent');
  });
</script>

<main class="home">
  <p class="label">smistress</p>
  <h1 class="display">Home</h1>
  <p class="muted">The chat surface arrives in a later milestone. For now, your dossier:</p>
  <nav class="spokes">
    <a href="/profile">Sub Profile</a>
    <a href="/character">Character</a>
    <a href="/settings">Settings &amp; well-being</a>
  </nav>
</main>

<style>
  .home {
    max-width: 640px;
    margin: 0 auto;
    padding: 32px 16px;
  }
  .muted {
    color: var(--muted);
  }
  .spokes {
    display: grid;
    gap: 8px;
    margin-top: 16px;
  }
  .spokes a {
    display: block;
    padding: 16px;
    border: 1px solid var(--hairline);
    color: var(--paper);
    text-decoration: none;
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .spokes a:hover {
    border-color: var(--accent);
  }
</style>
