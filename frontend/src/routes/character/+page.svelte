<script lang="ts">
  import SpokeHeader from '$lib/spokes/SpokeHeader.svelte';
  import Character from '$lib/onboarding/Character.svelte';
  import { session } from '$lib/stores/session.svelte';
  import { getCharacter, putCharacter } from '$lib/api/profile';

  type Char = {
    name: string | null;
    honorific: string;
    address_term: string;
    pronouns: string;
    archetype_blend: Record<string, number>;
    warmth: number;
    strictness: number;
    sadism: number;
    formality: number;
    verbosity: number;
    crudeness: number;
    wit: number;
  };

  let char = $state<Char | null>(null);
  let editing = $state(false);
  let saved = $state(false);

  async function load() {
    if (!session.profileId) return;
    char = (await getCharacter(session.profileId)) as Char;
  }
  $effect(() => {
    load();
  });

  async function onSave(patch: Record<string, unknown>) {
    await putCharacter(session.profileId!, patch);
    editing = false;
    saved = true;
    setTimeout(() => (saved = false), 2000);
    await load();
  }

  const DIALS = ['warmth', 'strictness', 'sadism', 'formality', 'verbosity', 'crudeness', 'wit'] as const;
</script>

<SpokeHeader title="Character" />

{#if !char}
  <p class="label pad">Loading…</p>
{:else if editing}
  <div class="pad">
    <Character onnext={onSave} initial={char} />
  </div>
{:else}
  <div class="pad">
    <div class="row">
      <h1 class="display">{char.honorific}</h1>
      <button class="edit" onclick={() => (editing = true)}>Edit</button>
    </div>
    {#if saved}<p class="ok label">saved</p>{/if}
    <p>She calls you <strong>{char.address_term}</strong> · {char.pronouns}</p>
    <ul class="ledger dials">
      {#each DIALS as d}
        <li>{d}: {char[d]}</li>
      {/each}
    </ul>
  </div>
{/if}

<style>
  .pad {
    max-width: 720px;
    margin: 0 auto;
    padding: 24px 16px;
  }
  .row {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .edit {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    background: transparent;
    color: var(--paper);
    border: 1px solid var(--paper);
    padding: 6px 12px;
    cursor: pointer;
  }
  .ok {
    color: var(--accent);
  }
  .dials {
    list-style: none;
    padding: 0;
    columns: 2;
  }
</style>
