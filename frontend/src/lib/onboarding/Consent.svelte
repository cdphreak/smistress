<script lang="ts">
  let { onnext }: {
    onnext: (data: { is_adult: boolean; consent_acknowledged: boolean }) => void;
  } = $props();
  let adult = $state(false);
  let consent = $state(false);
  const ready = $derived(adult && consent);
</script>

<h2 class="display">The frame</h2>
<p>This is an adult, consensual training tool. Acknowledge to begin.</p>
<label
  ><input type="checkbox" aria-label="I am 18 or older" bind:checked={adult} /> I am 18 or older.</label
>
<label
  ><input type="checkbox" aria-label="I consent" bind:checked={consent} /> I consent and understand I
  may stop at any time.</label
>
<button disabled={!ready} onclick={() => onnext({ is_adult: adult, consent_acknowledged: consent })}
  >Begin</button
>
