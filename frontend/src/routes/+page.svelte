<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { session } from '$lib/stores/session.svelte';
  import { chat } from '$lib/stores/chat.svelte';
  import { dossier } from '$lib/stores/dossier.svelte';
  import { safety } from '$lib/stores/safety.svelte';
  import { isSafeword } from '$lib/safety/phrases';
  import Bubble from '$lib/design/components/Bubble.svelte';
  import ActionCard from '$lib/chat/ActionCard.svelte';
  import DossierBar from '$lib/chat/DossierBar.svelte';

  let draft = $state('');

  onMount(async () => {
    if (!session.profileId) {
      await goto('/onboarding/consent');
      return;
    }
    await Promise.all([chat.load(), dossier.refresh()]);
  });

  async function send() {
    const text = draft.trim();
    if (!text) return;
    draft = '';
    // Typed safeword = emergency exit: intercept before any chat call (Addendum A6).
    if (isSafeword(text)) {
      await safety.confirmStop();
      return;
    }
    await chat.send(text);
    await dossier.refresh(); // her reply may have shifted standing
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }
</script>

<div class="home">
  <DossierBar data={dossier.data} />

  <main class="stream">
    {#each chat.messages as m (m.id)}
      <Bubble role={m.role} content={m.content} />
      {#if m.action}
        <ActionCard action={m.action} />
      {/if}
    {/each}
    {#if chat.messages.length === 0}
      <p class="empty label">She is waiting. Say something.</p>
    {/if}
  </main>

  <footer class="composer">
    <textarea
      placeholder="Say something to her…"
      value={draft}
      oninput={(e) => (draft = (e.currentTarget as HTMLTextAreaElement).value)}
      onkeydown={onKey}
      rows="2"
    ></textarea>
    <button class="send" disabled={chat.sending} onclick={send}>Send</button>
  </footer>
</div>

<style>
  .home {
    display: flex;
    flex-direction: column;
    height: 100dvh;
  }
  .stream {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    max-width: 720px;
    width: 100%;
    margin: 0 auto;
    padding: 16px;
  }
  .empty {
    margin: auto;
    color: var(--muted);
  }
  .composer {
    display: flex;
    gap: 8px;
    padding: 12px 16px;
    border-top: 1px solid var(--hairline);
    max-width: 720px;
    width: 100%;
    margin: 0 auto;
  }
  textarea {
    flex: 1;
    background: var(--raised);
    color: var(--paper);
    border: 1px solid var(--hairline);
    padding: 10px;
    border-radius: 0;
    resize: none;
    font-family: var(--font-body);
  }
  .send {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    background: var(--paper);
    color: var(--ink);
    border: 0;
    padding: 0 20px;
    cursor: pointer;
  }
  .send:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
