<script lang="ts">
  let { title }: { title: string } = $props();
</script>

<header class="spoke-head">
  <a class="label" href="/">← Home</a>
  <h1 class="display">{title}</h1>
</header>

<style>
  .spoke-head {
    display: flex;
    align-items: baseline;
    gap: 16px;
    padding: 16px;
    border-bottom: 1px solid var(--hairline);
  }
  a.label {
    color: var(--muted);
    text-decoration: none;
  }
  h1 {
    margin: 0;
    font-size: 1.4rem;
  }
</style>
