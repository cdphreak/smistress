<script lang="ts">
  import TextField from '$lib/design/components/TextField.svelte';
  import Scale from '$lib/design/components/Scale.svelte';

  type Patch = {
    honorific: string;
    address_term: string;
    warmth: number;
    strictness: number;
    sadism: number;
    formality: number;
    verbosity: number;
    crudeness: number;
    wit: number;
  };
  let { onnext }: { onnext: (patch: Patch) => void } = $props();

  // Seeded with the persona defaults (Governess-leaning, strict, witty).
  let honorific = $state('Mistress');
  let address_term = $state('pet');
  const DIALS = [
    'warmth',
    'strictness',
    'sadism',
    'formality',
    'verbosity',
    'crudeness',
    'wit'
  ] as const;
  type Dial = (typeof DIALS)[number];
  let dials = $state<Record<Dial, number>>({
    warmth: 40,
    strictness: 80,
    sadism: 30,
    formality: 70,
    verbosity: 50,
    crudeness: 30,
    wit: 75
  });
</script>

<h2 class="display">Shape her</h2>
<p class="label">Her name, how she addresses you, and the dials of her voice.</p>
<TextField label="Honorific" value={honorific} oninput={(v) => (honorific = v)} />
<TextField label="What she calls you" value={address_term} oninput={(v) => (address_term = v)} />

<div class="dials">
  {#each DIALS as d}
    <div class="dial">
      <span class="label">{d} · {dials[d]}</span>
      <Scale min={0} max={100} value={dials[d]} onchange={(v) => (dials = { ...dials, [d]: v })} />
    </div>
  {/each}
</div>

<button onclick={() => onnext({ honorific, address_term, ...dials })}>Next</button>

<style>
  .dials {
    display: grid;
    gap: 12px;
    margin: 16px 0;
  }
</style>
