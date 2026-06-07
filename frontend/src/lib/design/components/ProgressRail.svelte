<script lang="ts">
  let { total, current }: { total: number; current: number } = $props();
</script>

<div class="rail">
  <span class="label ledger">{current} / {total}</span>
  <div class="ticks">
    {#each Array(total) as _, i}
      <span class="tick" class:done={i < current}></span>
    {/each}
  </div>
</div>

<style>
  .rail {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .ticks {
    display: flex;
    gap: 4px;
  }
  .tick {
    width: 18px;
    height: 2px;
    background: var(--hairline);
  }
  .tick.done {
    background: var(--accent);
  }
</style>
