<script lang="ts">
  let { label, value, options, onchange }: {
    label: string;
    value: string;
    options: { value: string; label: string }[];
    onchange: (v: string) => void;
  } = $props();
</script>

<label class="field">
  <span class="label">{label}</span>
  <select {value} onchange={(e) => onchange((e.currentTarget as HTMLSelectElement).value)}>
    {#each options as o}
      <option value={o.value}>{o.label}</option>
    {/each}
  </select>
</label>

<style>
  .field {
    display: block;
  }
  select {
    width: 100%;
    background: var(--raised);
    color: var(--paper);
    border: 1px solid var(--hairline);
    padding: 10px;
    border-radius: 0;
    font-family: var(--font-body);
  }
</style>
