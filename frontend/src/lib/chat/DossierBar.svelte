<script lang="ts">
  import type { Dossier } from '$lib/api/dossier';
  import { supervision } from '$lib/stores/supervision.svelte';
  import ModeSheet from './ModeSheet.svelte';
  let { data }: { data: Dossier | null } = $props();
  let expanded = $state(false);
  let modeOpen = $state(false);

  async function openModes() {
    await supervision.refresh();
    modeOpen = true;
  }
</script>

<header class="dossier">
  {#if !data}
    <span class="label">…</span>
  {:else}
    <button class="summary" onclick={() => (expanded = !expanded)}>
      <span class="ledger">{data.rank} · merit {data.merit} · tokens {data.tokens} · debt {data.debt}</span>
      <span class="task">
        {#if data.active_task}
          {data.active_task.description} · intensity {data.active_task.intensity} · {data.active_task.discreetness}
        {:else}
          no active task
        {/if}
      </span>
    </button>
    <div class="meta">
      <button class="mode-badge" onclick={openModes}>mode · {data.supervision_mode}</button>
      <p class="disposition ledger">{data.disposition.line}</p>
    </div>
    {#if expanded}
      <div class="expand">
        <p class="ledger">
          chastity: {data.chastity.locked
            ? `locked · ${Math.floor(data.chastity.seconds_remaining / 3600)}h left`
            : 'not locked'}
        </p>
        <nav class="spokes">
          <a href="/profile">Sub Profile</a>
          <a href="/character">Character</a>
          <a href="/settings">Settings</a>
        </nav>
      </div>
    {/if}
  {/if}
  <ModeSheet open={modeOpen} onclose={() => (modeOpen = false)} />
</header>

<style>
  .dossier {
    position: sticky;
    top: 0;
    z-index: 10;
    background: var(--ink);
    border-bottom: 1px solid var(--hairline);
    padding: 12px 16px;
  }
  .summary {
    width: 100%;
    display: flex;
    justify-content: space-between;
    gap: 12px;
    background: transparent;
    border: 0;
    color: var(--paper);
    cursor: pointer;
    font: inherit;
    text-align: left;
  }
  .ledger {
    font-family: var(--font-mono);
  }
  .task {
    color: var(--muted);
  }
  .disposition {
    margin: 6px 0 0;
    color: var(--muted);
    font-size: 0.8rem;
  }
  .expand {
    margin-top: 10px;
  }
  .spokes {
    display: flex;
    gap: 16px;
  }
  .spokes a {
    color: var(--accent);
    text-decoration: none;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.75rem;
  }
  .meta {
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-top: 6px;
  }
  .mode-badge {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.7rem;
    background: transparent;
    color: var(--accent);
    border: 1px solid var(--accent);
    padding: 2px 8px;
    cursor: pointer;
    border-radius: 0;
  }
</style>
