<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import Consent from '$lib/onboarding/Consent.svelte';
  import Archetype from '$lib/onboarding/Archetype.svelte';
  import KinkSheet from '$lib/onboarding/KinkSheet.svelte';
  import { createProfile, getQuestionnaire, type Questionnaire } from '$lib/api/onboarding';
  import { submitArchetype, putKinks, type KinkRating } from '$lib/api/profile';
  import { session } from '$lib/stores/session.svelte';
  import { onboardingDraft } from '$lib/stores/onboardingDraft.svelte';
  import { nextStep, type Step } from '$lib/onboarding/steps';

  const step = $derived((page.params.step ?? 'consent') as Step);

  let questionnaire = $state<Questionnaire | null>(null);

  // The questionnaire (archetype statements + kink vocabulary) is fetched once
  // and reused across the archetype and kinks steps.
  $effect(() => {
    if ((step === 'archetype' || step === 'kinks') && !questionnaire) {
      getQuestionnaire().then((q) => (questionnaire = q));
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
{:else}
  <p>step: {step}</p>
{/if}
