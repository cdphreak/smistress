<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import Consent from '$lib/onboarding/Consent.svelte';
  import Archetype from '$lib/onboarding/Archetype.svelte';
  import KinkSheet from '$lib/onboarding/KinkSheet.svelte';
  import Toys from '$lib/onboarding/Toys.svelte';
  import SoContext from '$lib/onboarding/SoContext.svelte';
  import Goals from '$lib/onboarding/Goals.svelte';
  import Character from '$lib/onboarding/Character.svelte';
  import Preferences from '$lib/onboarding/Preferences.svelte';
  import Reveal from '$lib/onboarding/Reveal.svelte';
  import { createProfile, getQuestionnaire, type Questionnaire } from '$lib/api/onboarding';
  import {
    submitArchetype,
    putKinks,
    addToy,
    putSoContext,
    addGoal,
    putCharacter,
    putPreferences,
    getCharacter,
    type KinkRating
  } from '$lib/api/profile';
  import { session } from '$lib/stores/session.svelte';
  import { onboardingDraft } from '$lib/stores/onboardingDraft.svelte';
  import { nextStep, type Step } from '$lib/onboarding/steps';

  const step = $derived((page.params.step ?? 'consent') as Step);

  let questionnaire = $state<Questionnaire | null>(null);
  let revealCharacter = $state<{ honorific: string; address_term: string } | null>(null);

  // The questionnaire (archetype statements + kink vocabulary) is fetched once
  // and reused across the archetype and kinks steps.
  $effect(() => {
    if ((step === 'archetype' || step === 'kinks') && !questionnaire) {
      getQuestionnaire().then((q) => (questionnaire = q));
    }
  });

  // On the final step, load the assembled character for the reveal.
  $effect(() => {
    if (step === 'reveal' && !revealCharacter && session.profileId) {
      getCharacter(session.profileId).then(
        (c) => (revealCharacter = c as { honorific: string; address_term: string })
      );
    }
  });

  async function advance(from: Step) {
    const n = nextStep(from);
    if (n) await goto(`/onboarding/${n}`);
  }

  async function onConsent(data: { is_adult: boolean; consent_acknowledged: boolean }) {
    const created = await createProfile(data);
    session.setProfileId(created.id);
    await advance('consent');
  }

  async function onArchetype(answers: Record<string, number>) {
    if (!session.profileId) return;
    await submitArchetype(session.profileId, answers);
    onboardingDraft.set('archetype', answers);
    await advance('archetype');
  }

  async function onKinks(entries: { kink: string; rating: KinkRating }[]) {
    if (!session.profileId) return;
    await putKinks(session.profileId, entries);
    onboardingDraft.set('kinks', entries);
    await advance('kinks');
  }

  async function onToys(toy: { name: string; type: string; intiface_capable?: boolean } | null) {
    if (!session.profileId) return;
    if (toy) {
      await addToy(session.profileId, toy);
      onboardingDraft.set('toys', toy);
    }
    await advance('toys');
  }

  async function onSo(ctx: { description?: string; values?: string; dynamic?: string }) {
    if (!session.profileId) return;
    await putSoContext(session.profileId, ctx);
    onboardingDraft.set('so', ctx);
    await advance('so');
  }

  async function onGoals(goal: { title: string; description?: string } | null) {
    if (!session.profileId) return;
    if (goal) {
      await addGoal(session.profileId, goal);
      onboardingDraft.set('goals', goal);
    }
    await advance('goals');
  }

  async function onCharacter(patch: Record<string, unknown>) {
    if (!session.profileId) return;
    await putCharacter(session.profileId, patch);
    onboardingDraft.set('character', patch);
    await advance('character');
  }

  async function onPreferences(prefs: {
    intensity_ceiling: number;
    aftercare_prefs: string | null;
  }) {
    if (!session.profileId) return;
    await putPreferences(session.profileId, prefs);
    onboardingDraft.set('preferences', prefs);
    await advance('preferences');
  }

  async function onEnter() {
    onboardingDraft.clear();
    await goto('/');
  }
</script>

{#if step === 'consent'}
  <Consent onnext={onConsent} />
{:else if step === 'archetype'}
  {#if questionnaire}
    <Archetype
      statements={questionnaire.statements}
      scale={questionnaire.answer_scale}
      onnext={onArchetype}
      initial={(onboardingDraft.get('archetype') as Record<string, number>) ?? {}}
    />
  {:else}
    <p class="label">Loading…</p>
  {/if}
{:else if step === 'kinks'}
  {#if questionnaire}
    <KinkSheet
      kinks={questionnaire.kinks}
      onnext={onKinks}
      initial={(onboardingDraft.get('kinks') as { kink: string; rating: KinkRating }[] | undefined)?.reduce(
        (acc, e) => ({ ...acc, [e.kink]: e.rating }),
        {} as Record<string, KinkRating>
      ) ?? {}}
    />
  {:else}
    <p class="label">Loading…</p>
  {/if}
{:else if step === 'toys'}
  <Toys onnext={onToys} />
{:else if step === 'so'}
  <SoContext onnext={onSo} />
{:else if step === 'goals'}
  <Goals onnext={onGoals} />
{:else if step === 'character'}
  <Character onnext={onCharacter} />
{:else if step === 'preferences'}
  <Preferences
    onnext={onPreferences}
    initial={(onboardingDraft.get('preferences') as {
      intensity_ceiling: number;
      aftercare_prefs: string | null;
    }) ?? { intensity_ceiling: 50, aftercare_prefs: '' }}
  />
{:else if step === 'reveal'}
  {#if revealCharacter}
    <Reveal character={revealCharacter} onenter={onEnter} />
  {:else}
    <p class="label">Assembling…</p>
  {/if}
{:else}
  <p>step: {step}</p>
{/if}
