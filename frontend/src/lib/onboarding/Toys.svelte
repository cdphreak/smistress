<script lang="ts">
  import TextField from '$lib/design/components/TextField.svelte';
  import Select from '$lib/design/components/Select.svelte';
  type Toy = {
    name: string;
    type: string;
    intiface_capable?: boolean;
    notes?: string;
    noise?: boolean;
    visibility?: boolean;
    discreet_capable?: boolean;
  };
  let {
    onnext,
    types = [],
    initial = null
  }: { onnext: (toy: Toy | null) => void; types?: string[]; initial?: Toy | null } = $props();

  let name = $state(initial?.name ?? '');
  let type = $state(initial?.type ?? '');
  let intiface = $state(initial?.intiface_capable ?? false);
  let noise = $state(initial?.noise ?? false);
  let visibility = $state(initial?.visibility ?? false);
  let discreet = $state(initial?.discreet_capable ?? false);
  const editing = $derived(initial !== null);
  const ready = $derived(name.trim().length > 0 && type.length > 0);
  const options = $derived([
    { value: '', label: 'Select a type…' },
    ...types.map((t) => ({ value: t, label: t.replaceAll('_', ' ') }))
  ]);

  function submit() {
    onnext({
      name,
      type,
      intiface_capable: intiface,
      noise,
      visibility,
      discreet_capable: discreet
    });
  }
</script>

<h2 class="display">{editing ? 'Edit toy' : 'Your toys'}</h2>
<p class="label">{editing ? 'Update its details.' : 'Add one now, or skip — you can add more later.'}</p>
<TextField label="Name" value={name} oninput={(v) => (name = v)} />
<Select label="Type" value={type} {options} onchange={(v) => (type = v)} />
<div class="flags">
  <label><input type="checkbox" bind:checked={intiface} /> Intiface-capable</label>
  <label><input type="checkbox" bind:checked={discreet} /> Discreet-capable (usable unseen)</label>
  <label><input type="checkbox" bind:checked={noise} /> Makes noise</label>
  <label><input type="checkbox" bind:checked={visibility} /> Visible when worn</label>
</div>
<div class="actions">
  {#if !editing}
    <button class="ghost" onclick={() => onnext(null)}>Skip</button>
  {/if}
  <button disabled={!ready} onclick={submit}>{editing ? 'Save' : 'Add & continue'}</button>
</div>

<style>
  .flags {
    display: grid;
    gap: 6px;
    margin: 12px 0;
  }
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
