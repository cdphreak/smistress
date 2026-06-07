<script lang="ts">
  import TextField from '$lib/design/components/TextField.svelte';
  import TextArea from '$lib/design/components/TextArea.svelte';
  type Goal = { title: string; description?: string };
  let { onnext }: { onnext: (goal: Goal | null) => void } = $props();
  let title = $state('');
  let description = $state('');
  const ready = $derived(title.trim().length > 0);
</script>

<h2 class="display">Your goals</h2>
<p class="label">Name one thing she should hold you to, or skip.</p>
<TextField label="Goal" value={title} oninput={(v) => (title = v)} />
<TextArea label="Details" value={description} oninput={(v) => (description = v)} />
<div class="actions">
  <button class="ghost" onclick={() => onnext(null)}>Skip</button>
  <button
    disabled={!ready}
    onclick={() => onnext({ title, description: description || undefined })}>Add &amp; continue</button
  >
</div>

<style>
  .actions {
    display: flex;
    gap: 12px;
    margin-top: 16px;
  }
  .ghost {
    background: transparent;
    color: var(--paper);
    border: 1px solid var(--paper);
  }
</style>
