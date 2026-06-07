<script lang="ts">
  import '$lib/design/tokens.css';
  import favicon from '$lib/assets/favicon.svg';
  import SafeButton from '$lib/safety/SafeButton.svelte';
  import StopSheet from '$lib/safety/StopSheet.svelte';
  import { session } from '$lib/stores/session.svelte';

  let { children } = $props();
</script>

<svelte:head>
  <link rel="icon" href={favicon} />
</svelte:head>

{@render children()}

<!-- Safety is a global overlay, never a route (Addendum A6). Shown once a profile exists. -->
{#if session.profileId}
  <SafeButton />
  <StopSheet />
{/if}
