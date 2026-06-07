<script lang="ts">
  let { label, value = '', oninput, placeholder = '' }: {
    label: string;
    value?: string;
    oninput: (v: string) => void;
    placeholder?: string;
  } = $props();
</script>

<label class="field">
  <span class="label">{label}</span>
  <input
    {value}
    {placeholder}
    oninput={(e) => oninput((e.currentTarget as HTMLInputElement).value)}
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
    border-radius: 0;
  }
</style>
