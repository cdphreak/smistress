<script lang="ts">
  let { name = 'world' }: { name?: string } = $props();
</script>
<p>hello {name}</p>
