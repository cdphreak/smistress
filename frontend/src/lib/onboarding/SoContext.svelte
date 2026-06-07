<script lang="ts">
  import TextArea from '$lib/design/components/TextArea.svelte';
  type Ctx = { description?: string; values?: string; dynamic?: string };
  let { onnext }: { onnext: (ctx: Ctx) => void } = $props();
  let description = $state('');
  let values = $state('');
  let dynamic = $state('');
</script>

<h2 class="display">Significant other</h2>
<p class="label">Context she should respect. All optional.</p>
<TextArea label="Who they are" value={description} oninput={(v) => (description = v)} />
<TextArea label="Shared values" value={values} oninput={(v) => (values = v)} />
<TextArea label="Your dynamic" value={dynamic} oninput={(v) => (dynamic = v)} />
<button
  onclick={() =>
    onnext({
      description: description || undefined,
      values: values || undefined,
      dynamic: dynamic || undefined
    })}>Next</button
>
