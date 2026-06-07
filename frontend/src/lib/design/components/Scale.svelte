<script lang="ts">
  let { min, max, value, onchange }: {
    min: number;
    max: number;
    value: number;
    onchange: (v: number) => void;
  } = $props();
</script>

<input
  type="range"
  {min}
  {max}
  step="1"
  value={String(value)}
  oninput={(e) => onchange(Number((e.currentTarget as HTMLInputElement).value))}
/>

<style>
  input {
    width: 100%;
    accent-color: var(--accent);
  }
</style>
