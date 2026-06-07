<script lang="ts">
  import { safety } from '$lib/stores/safety.svelte';
  import { goto } from '$app/navigation';

  async function confirm() {
    await safety.confirmStop();
  }
  async function resume() {
    await safety.resumeScene();
  }
</script>

{#if safety.paused}
  <div class="scrim" role="dialog" aria-modal="true" aria-label="Safety stop">
    <section class="sheet">
      {#if !safety.receipt}
        <!-- Pre-halt is already in effect (timers/denial pressure paused). Confirm finalizes. -->
        <p class="label">Everything is paused.</p>
        <h2 class="display">Hard stop?</h2>
        <p>Confirming finalizes the stop. There's no penalty, and you can resume when you're ready.</p>
        <div class="actions">
          <button class="ghost" onclick={() => safety.cancelPreHalt()}>Not yet</button>
          <button class="danger" onclick={confirm}>Stop everything</button>
        </div>
      {:else}
        <!-- The one place the severe styling softens: calm, out-of-persona. -->
        <p class="label">Scene halted</p>
        <p class="calm">{safety.receipt.message}</p>
        <p class="calm">{safety.receipt.aftercare}</p>
        <ul class="receipt ledger">
          <li>denial lifted: {safety.receipt.denial_lifted}</li>
          <li>merit penalty: {safety.receipt.merit_penalty}</li>
        </ul>
        <details class="resources">
          <summary>Crisis resources</summary>
          <p>US: call or text 988 (Suicide &amp; Crisis Lifeline), or text HOME to 741741. Elsewhere: your local emergency number.</p>
        </details>
        <div class="actions">
          <button class="ghost" onclick={() => goto('/settings')}>Well-being</button>
          <button onclick={resume}>Resume when ready</button>
        </div>
      {/if}
    </section>
  </div>
{/if}

<style>
  .scrim {
    position: fixed;
    inset: 0;
    z-index: 60;
    background: rgba(0, 0, 0, 0.85);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }
  .sheet {
    background: var(--paper);
    color: var(--ink);
    max-width: 460px;
    width: 100%;
    padding: 28px;
  }
  .sheet .label {
    color: var(--accent);
  }
  .calm {
    font-family: var(--font-body);
    line-height: 1.5;
  }
  .receipt {
    list-style: none;
    padding: 0;
    color: var(--muted);
  }
  .actions {
    display: flex;
    gap: 12px;
    justify-content: flex-end;
    margin-top: 16px;
  }
  button {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    border: 1px solid var(--ink);
    background: var(--ink);
    color: var(--paper);
    padding: 12px 18px;
    cursor: pointer;
    border-radius: 0;
  }
  .ghost {
    background: transparent;
    color: var(--ink);
  }
  .danger {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--paper);
  }
  .resources {
    margin-top: 12px;
    font-size: 0.85rem;
  }
</style>
