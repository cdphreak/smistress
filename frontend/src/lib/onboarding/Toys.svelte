<script lang="ts">
  import TextField from '$lib/design/components/TextField.svelte';
  type Toy = { name: string; type: string; intiface_capable?: boolean; notes?: string };
  let { onnext }: { onnext: (toy: Toy | null) => void } = $props();
  let name = $state('');
  let type = $state('');
  let intiface = $state(false);
  const ready = $derived(name.trim().length > 0 && type.trim().length > 0);
</script>

<h2 class="display">Your toys</h2>
<p class="label">Add one now, or skip — you can add more later.</p>
<TextField label="Name" value={name} oninput={(v) => (name = v)} />
<TextField label="Type" value={type} oninput={(v) => (type = v)} />
<label
  ><input type="checkbox" aria-label="Intiface capable" bind:checked={intiface} /> Intiface-capable</label
>
<div class="actions">
  <button class="ghost" onclick={() => onnext(null)}>Skip</button>
  <button
    disabled={!ready}
    onclick={() => onnext({ name, type, intiface_capable: intiface })}>Add &amp; continue</button
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
