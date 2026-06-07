<script lang="ts">
  import { untrack } from 'svelte';
  import SegmentedControl from '$lib/design/components/SegmentedControl.svelte';
  import type { KinkRating } from '$lib/api/profile';

  let { kinks, onnext, initial = {} }: {
    kinks: string[];
    onnext: (entries: { kink: string; rating: KinkRating }[]) => void;
    initial?: Record<string, KinkRating>;
  } = $props();

  const OPTIONS = [
    { value: 'favorite', label: 'Fav' },
    { value: 'like', label: 'Like' },
    { value: 'curious', label: 'Curious' },
    { value: 'soft_limit', label: 'Soft', tone: 'danger-muted' as const },
    { value: 'hard_limit', label: 'Hard', tone: 'danger' as const },
    { value: 'na', label: 'N-A' }
  ];

  // Seed once; the user then mutates `ratings` per row.
  let ratings = $state<Record<string, KinkRating>>(
    untrack(() => Object.fromEntries(kinks.map((k) => [k, initial[k] ?? 'na'])))
  );

  function submit() {
    const entries = kinks
      .filter((k) => ratings[k] !== 'na')
      .map((k) => ({ kink: k, rating: ratings[k] }));
    onnext(entries);
  }
</script>

<h2 class="display">Your limits</h2>
<p class="label">Hard-limits are never crossed. Soft-limits are approached only with care.</p>
<ul class="grid">
  {#each kinks as k}
    <li class="row">
      <span class="name">{k.replaceAll('_', ' ')}</span>
      <SegmentedControl
        options={OPTIONS}
        value={ratings[k]}
        onchange={(v) => (ratings = { ...ratings, [k]: v as KinkRating })}
      />
    </li>
  {/each}
</ul>
<button onclick={submit}>Next</button>

<style>
  .grid {
    list-style: none;
    padding: 0;
    display: grid;
    gap: 8px;
  }
  .row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    border-bottom: 1px solid var(--hairline);
    padding: 6px 0;
  }
  .name {
    text-transform: capitalize;
  }
</style>
