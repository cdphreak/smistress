<script lang="ts">
  import { safety } from '$lib/stores/safety.svelte';
</script>

<button class="safe" aria-label="SAFE — stop everything" onclick={() => safety.preHalt()}>
  SAFE
</button>

<style>
  .safe {
    position: fixed;
    bottom: 16px;
    right: 16px;
    z-index: 50;
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    background: var(--accent);
    color: var(--paper);
    border: 0;
    border-radius: 0;
    padding: 14px 22px;
    cursor: pointer;
    box-shadow: 0 0 0 2px var(--ink);
  }
</style>
