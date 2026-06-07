<script lang="ts">
  let { character, onenter }: {
    character: { honorific: string; address_term: string };
    onenter?: () => void;
  } = $props();
</script>

<section class="reveal">
  <p class="label">Intake complete</p>
  <h1 class="display">{character.honorific}</h1>
  <p>She has read your file, {character.address_term}. She is ready when you are.</p>
  {#if onenter}
    <button onclick={() => onenter()}>Enter</button>
  {/if}
</section>

<style>
  .reveal {
    text-align: center;
    padding: 48px 0;
  }
  h1 {
    font-size: 2.4rem;
    color: var(--accent);
  }
</style>
