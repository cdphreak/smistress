<script lang="ts">
  import { untrack } from 'svelte';
  import NumberField from '$lib/design/components/NumberField.svelte';
  import TextArea from '$lib/design/components/TextArea.svelte';
  let { onnext, initial = { intensity_ceiling: 50, aftercare_prefs: '' } }: {
    onnext: (p: { intensity_ceiling: number; aftercare_prefs: string | null }) => void;
    initial?: { intensity_ceiling: number; aftercare_prefs: string | null };
  } = $props();
  // Seed once from the initial prop; the user then edits these directly.
  let ceiling = $state(untrack(() => initial.intensity_ceiling));
  let aftercare = $state(untrack(() => initial.aftercare_prefs ?? ''));
</script>

<h2 class="display">Your boundaries</h2>
<NumberField label="Intensity ceiling (0–100)" value={ceiling} oninput={(v) => (ceiling = v)} />
<TextArea label="Aftercare preferences" value={aftercare} oninput={(v) => (aftercare = v)} />
<button onclick={() => onnext({ intensity_ceiling: ceiling, aftercare_prefs: aftercare || null })}
  >Next</button
>
