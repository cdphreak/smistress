<script lang="ts">
  let {
    label,
    onclick,
    disabled = false,
    variant = 'solid'
  }: {
    label: string;
    onclick?: () => void;
    disabled?: boolean;
    variant?: 'solid' | 'ghost' | 'danger';
  } = $props();
</script>

<button class="btn {variant}" {disabled} onclick={() => onclick?.()}>{label}</button>

<style>
  .btn {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    border: 1px solid var(--paper);
    background: var(--paper);
    color: var(--ink);
    padding: 12px 20px;
    cursor: pointer;
    border-radius: 0;
  }
  .ghost {
    background: transparent;
    color: var(--paper);
  }
  .danger {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--paper);
  }
  .btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
