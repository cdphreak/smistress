<script lang="ts">
  import TextArea from '$lib/design/components/TextArea.svelte';
  import { supervision } from '$lib/stores/supervision.svelte';
  import { dossier } from '$lib/stores/dossier.svelte';
  import type { SupervisionMode } from '$lib/api/supervision';

  let { open = false, onclose }: { open?: boolean; onclose: () => void } = $props();

  const MODES: { value: SupervisionMode; label: string; meaning: string }[] = [
    { value: 'full', label: 'Full', meaning: 'Fully available — at her mercy anytime.' },
    { value: 'discreet', label: 'Discreet', meaning: 'Family around — quiet, low-visibility only.' },
    { value: 'task', label: 'Task', meaning: 'Tasks only, with graceful fulfilment timers.' },
    { value: 'homeoffice', label: 'Homeoffice', meaning: 'Meetings — fully covert content only.' },
    { value: 'vacation', label: 'Vacation', meaning: 'Training paused — economy frozen.' }
  ];

  let note = $state('');
  // Keep the note box in sync with the active mode's stored note.
  $effect(() => {
    note = supervision.notes[supervision.mode] ?? '';
  });

  async function choose(mode: SupervisionMode) {
    await supervision.setMode(mode);
    await dossier.refresh(); // badge reads the dossier
  }
  async function saveNote() {
    await supervision.setNote(supervision.mode, note);
  }
</script>

{#if open}
  <div class="scrim" role="dialog" aria-modal="true" aria-label="Supervision mode">
    <section class="sheet">
      <p class="label">Supervision mode</p>
      <ul class="modes">
        {#each MODES as m}
          <li>
            <button
              class="mode"
              class:active={supervision.mode === m.value}
              class:frozen={m.value === 'vacation'}
              onclick={() => choose(m.value)}
            >
              <span class="name">{m.label}</span>
              <span class="meaning">{m.meaning}</span>
            </button>
          </li>
        {/each}
      </ul>

      <TextArea
        label={`Note for "${supervision.mode}" mode`}
        value={note}
        oninput={(v) => (note = v)}
      />
      <div class="actions">
        <button class="ghost" onclick={onclose}>Close</button>
        <button onclick={saveNote}>Save note</button>
      </div>
    </section>
  </div>
{/if}

<style>
  .scrim {
    position: fixed;
    inset: 0;
    z-index: 50;
    background: rgba(0, 0, 0, 0.85);
    display: flex;
    align-items: flex-end;
    justify-content: center;
    padding: 16px;
  }
  .sheet {
    background: var(--paper);
    color: var(--ink);
    max-width: 460px;
    width: 100%;
    padding: 24px;
  }
  .label {
    color: var(--accent);
  }
  .modes {
    list-style: none;
    padding: 0;
    display: grid;
    gap: 8px;
    margin: 12px 0;
  }
  .mode {
    width: 100%;
    text-align: left;
    display: grid;
    gap: 2px;
    background: transparent;
    border: 1px solid var(--hairline);
    border-radius: 0;
    color: var(--ink);
    padding: 10px 12px;
    cursor: pointer;
  }
  .mode.active {
    border-color: var(--accent);
    background: var(--accent);
    color: var(--paper);
  }
  .mode.frozen .name::after {
    content: ' · frozen';
    color: var(--accent);
  }
  .mode.active.frozen .name::after {
    color: var(--paper);
  }
  .name {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .meaning {
    font-size: 0.8rem;
    color: var(--muted);
  }
  .mode.active .meaning {
    color: var(--paper);
  }
  .actions {
    display: flex;
    gap: 12px;
    justify-content: flex-end;
    margin-top: 12px;
  }
  button {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    border: 1px solid var(--ink);
    border-radius: 0;
    background: var(--ink);
    color: var(--paper);
    padding: 10px 16px;
    cursor: pointer;
  }
  .ghost {
    background: transparent;
    color: var(--ink);
  }
</style>
