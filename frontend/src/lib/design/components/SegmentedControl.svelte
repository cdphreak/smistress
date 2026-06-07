<script lang="ts">
  type Opt = { value: string; label: string; tone?: 'normal' | 'danger' | 'danger-muted' };
  let { options, value, onchange }: {
    options: Opt[];
    value: string | null;
    onchange: (v: string) => void;
  } = $props();
</script>

<div class="seg">
  {#each options as o}
    <button
      class="opt {o.tone ?? 'normal'}"
      class:selected={o.value === value}
      onclick={() => onchange(o.value)}
    >{o.label}</button>
  {/each}
</div>

<style>
  .seg {
    display: inline-flex;
    border: 1px solid var(--hairline);
  }
  .opt {
    font-family: var(--font-mono);
    font-size: 0.72rem;
    text-transform: uppercase;
    background: var(--ink);
    color: var(--muted);
    border: 0;
    border-right: 1px solid var(--hairline);
    padding: 6px 10px;
    cursor: pointer;
  }
  .opt:last-child {
    border-right: 0;
  }
  .opt.selected {
    background: var(--paper);
    color: var(--ink);
  }
  .opt.danger.selected {
    background: var(--accent);
    color: var(--paper);
  }
  .opt.danger-muted.selected {
    background: var(--accent-muted);
    color: var(--paper);
  }
</style>
