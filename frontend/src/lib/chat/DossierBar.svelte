<script lang="ts">
  import type { Dossier } from '$lib/api/dossier';
  let { data }: { data: Dossier | null } = $props();
  let expanded = $state(false);
</script>

<header class="dossier">
  {#if !data}
    <span class="label">…</span>
  {:else}
    <button class="summary" onclick={() => (expanded = !expanded)}>
      <span class="ledger">{data.rank} · merit {data.merit} · tokens {data.tokens} · debt {data.debt}</span>
      <span class="task">{data.active_task ? data.active_task.description : 'no active task'}</span>
    </button>
    <p class="disposition ledger">{data.disposition.line}</p>
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
</style>
