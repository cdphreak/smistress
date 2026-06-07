<script lang="ts">
  import { goto } from '$app/navigation';
  import SpokeHeader from '$lib/spokes/SpokeHeader.svelte';
  import TextField from '$lib/design/components/TextField.svelte';
  import SegmentedControl from '$lib/design/components/SegmentedControl.svelte';
  import { session } from '$lib/stores/session.svelte';
  import {
    getSafety, setHiatus, lowerLimit, consentCheck, deleteProfile, type SafetyState
  } from '$lib/api/safety';
  import type { KinkRating } from '$lib/api/profile';

  let safetyState = $state<SafetyState | null>(null);
  let limitKink = $state('');
  let limitRating = $state<'soft_limit' | 'hard_limit'>('hard_limit');
  let confirmingDelete = $state(false);
  let note = $state<string | null>(null);

  async function load() {
    if (!session.profileId) return;
    safetyState = await getSafety(session.profileId);
  }
  $effect(() => {
    load();
  });

  function flash(msg: string) {
    note = msg;
    setTimeout(() => (note = null), 2500);
  }
  async function toggleHiatus() {
    safetyState = await setHiatus(session.profileId!, !(safetyState?.on_hiatus ?? false));
    flash(safetyState.on_hiatus ? 'Training paused.' : 'Training resumed.');
  }
  async function tightenLimit() {
    if (!limitKink.trim()) return;
    await lowerLimit(session.profileId!, limitKink.trim(), limitRating as KinkRating);
    flash(`"${limitKink}" set to ${limitRating.replace('_', ' ')}.`);
    limitKink = '';
  }
  async function acknowledgeConsent() {
    safetyState = await consentCheck(session.profileId!);
    flash('Consent check-in recorded.');
  }
  async function reallyDelete() {
    await deleteProfile(session.profileId!);
    session.clear();
    await goto('/onboarding/consent');
  }
</script>

<SpokeHeader title="Settings & well-being" />

<div class="pad sections">
  {#if note}<p class="ok label">{note}</p>{/if}

  <section>
    <h2 class="label">Hiatus</h2>
    <p class="muted">Pause training with no penalty. Nothing counts against you while paused.</p>
    <button class="ctl" onclick={toggleHiatus}>
      {safetyState?.on_hiatus ? 'Resume training' : 'Pause training (hiatus)'}
    </button>
  </section>

  <section>
    <h2 class="label">Tighten a limit</h2>
    <p class="muted">Honored immediately — she sees the change on her next turn.</p>
    <TextField label="Kink" value={limitKink} oninput={(v) => (limitKink = v)} />
    <div class="seg">
      <SegmentedControl
        options={[
          { value: 'soft_limit', label: 'Soft', tone: 'danger-muted' },
          { value: 'hard_limit', label: 'Hard', tone: 'danger' }
        ]}
        value={limitRating}
        onchange={(v) => (limitRating = v as 'soft_limit' | 'hard_limit')}
      />
    </div>
    <button class="ctl" onclick={tightenLimit}>Apply</button>
  </section>

  <section>
    <h2 class="label">Consent check-in</h2>
    {#if safetyState?.consent_check_due}
      <p class="due">Check-in due — is this still right for you?</p>
    {:else}
      <p class="muted">Up to date.</p>
    {/if}
    <button class="ctl" onclick={acknowledgeConsent}>I'm still in</button>
  </section>

  <section class="danger-zone">
    <h2 class="label">Delete everything</h2>
    <p class="muted">Permanently erases your profile and all data. This cannot be undone.</p>
    {#if !confirmingDelete}
      <button class="ctl danger" onclick={() => (confirmingDelete = true)}>Delete everything</button>
    {:else}
      <p class="due">Are you absolutely sure?</p>
      <div class="actions">
        <button class="ctl" onclick={() => (confirmingDelete = false)}>Cancel</button>
        <button class="ctl danger" onclick={reallyDelete}>Yes, delete it all</button>
      </div>
    {/if}
  </section>
</div>

<style>
  .pad {
    max-width: 640px;
    margin: 0 auto;
    padding: 24px 16px;
  }
  .sections {
    display: grid;
    gap: 28px;
  }
  .muted {
    color: var(--muted);
  }
  .due {
    color: var(--accent);
  }
  .ok {
    color: var(--accent);
  }
  .seg {
    margin: 8px 0;
  }
  .ctl {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    background: var(--paper);
    color: var(--ink);
    border: 1px solid var(--paper);
    padding: 12px 18px;
    cursor: pointer;
    margin-top: 8px;
  }
  .ctl.danger {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--paper);
  }
  .actions {
    display: flex;
    gap: 12px;
  }
  .danger-zone {
    border: 1px solid var(--accent-muted);
    padding: 16px;
  }
</style>
