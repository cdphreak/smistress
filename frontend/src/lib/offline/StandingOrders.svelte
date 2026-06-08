<script lang="ts">
  import type { DroneNotice } from '$lib/api/drones';
  let { notices }: { notices: DroneNotice[] } = $props();
</script>

<section class="orders">
  <p class="away label">She is away. Her drones hold your standing orders.</p>
  {#each notices as n, i (i)}
    <div class="notice">
      <span class="unit">{n.unit}</span>
      <span class="line">{n.line}</span>
    </div>
  {/each}
</section>

<style>
  .orders {
    max-width: 720px;
    width: 100%;
    margin: 0 auto;
    padding: 16px;
  }
  .away {
    color: var(--muted);
    margin: 8px 0 16px;
  }
  /* Cold, mechanical: gray, monospace, unit-labeled — deliberately unlike her
     crimson-hairline bubbles, so her live presence reads as earned (Addendum B3). */
  .notice {
    display: flex;
    gap: 12px;
    align-items: baseline;
    background: var(--raised);
    border-left: 2px solid var(--muted);
    padding: 10px 14px;
    margin: 8px 0;
    font-family: var(--font-mono);
  }
  .unit {
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.7rem;
    color: var(--muted);
    flex: 0 0 auto;
  }
  .line {
    color: var(--paper);
    font-size: 0.85rem;
    line-height: 1.5;
  }
</style>
