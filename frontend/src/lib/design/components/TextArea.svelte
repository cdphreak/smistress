<script lang="ts">
  let { label, value = '', oninput }: {
    label: string;
    value?: string;
    oninput: (v: string) => void;
  } = $props();
</script>

<label class="field">
  <span class="label">{label}</span>
  <textarea
    {value}
    rows="3"
    oninput={(e) => oninput((e.currentTarget as HTMLTextAreaElement).value)}
  ></textarea>
</label>

<style>
  .field {
    display: block;
  }
  textarea {
    width: 100%;
    background: var(--raised);
    color: var(--paper);
    border: 1px solid var(--hairline);
    padding: 10px;
    border-radius: 0;
    font-family: var(--font-body);
  }
</style>
