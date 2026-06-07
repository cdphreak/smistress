<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import Consent from '$lib/onboarding/Consent.svelte';
  import { createProfile } from '$lib/api/onboarding';
  import { session } from '$lib/stores/session.svelte';
  import { nextStep, type Step } from '$lib/onboarding/steps';

  const step = $derived((page.params.step ?? 'consent') as Step);

  async function advance(from: Step) {
    const n = nextStep(from);
    if (n) await goto(`/onboarding/${n}`);
  }

  async function onConsent(data: { is_adult: boolean; consent_acknowledged: boolean }) {
    const created = await createProfile(data);
    session.setProfileId(created.id);
    await advance('consent');
  }
</script>

{#if step === 'consent'}
  <Consent onnext={onConsent} />
{:else}
  <p>step: {step}</p>
{/if}
