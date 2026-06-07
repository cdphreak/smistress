<script lang="ts">
  let { label, value, min = 0, max = 100, oninput }: {
    label: string;
    value: number;
    min?: number;
    max?: number;
    oninput: (v: number) => void;
  } = $props();
</script>

<label class="field">
  <span class="label">{label}</span>
  <input
    type="number"
    value={String(value)}
    {min}
    {max}
    oninput={(e) => oninput(Number((e.currentTarget as HTMLInputElement).value))}
  />
</label>

<style>
  .field {
    display: block;
  }
  input {
    width: 100%;
    background: var(--raised);
    color: var(--paper);
    border: 1px solid var(--hairline);
    padding: 10px;
    font-family: var(--font-mono);
  }
</style>
