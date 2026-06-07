<script lang="ts">
  let { role, content }: { role: 'user' | 'assistant'; content: string } = $props();
  const mine = $derived(role === 'user');
</script>

<div class="bubble {mine ? 'sub' : 'mistress'}">{content}</div>

<style>
  .bubble {
    max-width: 78%;
    padding: 10px 14px;
    margin: 6px 0;
    line-height: 1.5;
    white-space: pre-wrap;
  }
  .mistress {
    align-self: flex-start;
    background: var(--raised);
    color: var(--paper);
    border-left: 2px solid var(--accent);
  }
  .sub {
    align-self: flex-end;
    background: #222;
    color: var(--paper);
  }
</style>
