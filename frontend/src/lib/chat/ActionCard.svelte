<script lang="ts">
  import type { ActionCard } from '$lib/api/chat';
  let { action }: { action: ActionCard } = $props();

  const title = $derived(
    action.error
      ? 'Action failed'
      : action.tool === 'assign_task'
        ? 'Task assigned'
        : action.tool === 'set_denial_timer'
          ? 'Denial set'
          : action.tool === 'grant_tokens'
            ? 'Tokens granted'
            : 'Action'
  );
</script>

<div class="card" class:err={!!action.error}>
  <span class="label">{title}</span>
  {#if action.error}
    <p>She couldn’t: {action.error}</p>
  {:else if action.tool === 'assign_task'}
    <p class="ledger">{action.description} · proof: {action.proof} · +{action.merit_reward} merit</p>
  {:else if action.tool === 'set_denial_timer'}
    <p class="ledger">{action.hours}h{action.reason ? ` · ${action.reason}` : ''}</p>
  {:else if action.tool === 'grant_tokens'}
    <p class="ledger">+{action.amount} tokens{action.reason ? ` · ${action.reason}` : ''}</p>
  {/if}
</div>

<style>
  .card {
    align-self: flex-start;
    max-width: 78%;
    margin: 2px 0 10px;
    padding: 8px 12px;
    border: 1px solid var(--accent);
    background: var(--ink);
  }
  .card.err {
    border-color: var(--accent-muted);
  }
  .ledger {
    font-family: var(--font-mono);
    margin: 4px 0 0;
    font-size: 0.85rem;
  }
</style>
