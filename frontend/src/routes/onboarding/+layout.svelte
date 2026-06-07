<script lang="ts">
  import { page } from '$app/state';
  import ProgressRail from '$lib/design/components/ProgressRail.svelte';
  import { STEPS, stepIndex } from '$lib/onboarding/steps';
  let { children } = $props();
  const current = $derived(stepIndex(page.params.step ?? 'consent') + 1);
</script>

<header class="wiz-head">
  <span class="label">Intake</span>
  <ProgressRail total={STEPS.length} {current} />
</header>
<main class="wiz-body">{@render children()}</main>

<style>
  .wiz-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px;
    border-bottom: 1px solid var(--hairline);
  }
  .wiz-body {
    max-width: 720px;
    margin: 0 auto;
    padding: 24px 16px;
  }
</style>
