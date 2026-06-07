<script lang="ts">
  import { untrack } from 'svelte';
  import Scale from '$lib/design/components/Scale.svelte';
  type S = { id: string; archetype: string; text: string };
  let { statements, scale, onnext, initial = {} }: {
    statements: S[];
    scale: { min: number; max: number };
    onnext: (answers: Record<string, number>) => void;
    initial?: Record<string, number>;
  } = $props();

  // Seed once from the initial props; the user then mutates `answers` directly.
  let answers = $state<Record<string, number>>(
    untrack(() => Object.fromEntries(statements.map((s) => [s.id, initial[s.id] ?? scale.min])))
  );
</script>

<h2 class="display">How you lean</h2>
<ol class="cards">
  {#each statements as s}
    <li class="card">
      <p>{s.text}</p>
      <Scale
        min={scale.min}
        max={scale.max}
        value={answers[s.id]}
        onchange={(v) => (answers = { ...answers, [s.id]: v })}
      />
    </li>
  {/each}
</ol>
<button onclick={() => onnext(answers)}>Next</button>

<style>
  .cards {
    list-style: none;
    padding: 0;
    display: grid;
    gap: 16px;
  }
  .card {
    background: var(--raised);
    border: 1px solid var(--hairline);
    padding: 16px;
  }
</style>
