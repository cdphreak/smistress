<script lang="ts">
  import SpokeHeader from '$lib/spokes/SpokeHeader.svelte';
  import KinkSheet from '$lib/onboarding/KinkSheet.svelte';
  import Toys from '$lib/onboarding/Toys.svelte';
  import Goals from '$lib/onboarding/Goals.svelte';
  import SoContext from '$lib/onboarding/SoContext.svelte';
  import Preferences from '$lib/onboarding/Preferences.svelte';
  import { session } from '$lib/stores/session.svelte';
  import { getProfile, putKinks, addToy, addGoal, putSoContext, putPreferences, type KinkRating } from '$lib/api/profile';
  import { getQuestionnaire } from '$lib/api/onboarding';

  type Kink = { kink: string; rating: KinkRating };
  type Profile = {
    intensity_ceiling: number;
    aftercare_prefs: string | null;
    archetype_scores: Record<string, number>;
    kinks: Kink[];
    toys: { name: string; type: string }[];
    goals: { title: string; description?: string }[];
    so_context: { description?: string; values?: string; dynamic?: string } | null;
    character: { honorific: string; address_term: string };
  };

  let profile = $state<Profile | null>(null);
  let kinkVocab = $state<string[]>([]);
  let editing = $state<string | null>(null);
  let saved = $state<string | null>(null);

  async function load() {
    if (!session.profileId) return;
    profile = (await getProfile(session.profileId)) as Profile;
  }
  $effect(() => {
    load();
  });

  async function ensureVocab() {
    if (kinkVocab.length === 0) {
      const q = await getQuestionnaire();
      kinkVocab = q.kinks;
    }
  }
  async function openKinks() {
    await ensureVocab();
    editing = 'kinks';
  }
  function flash(section: string) {
    saved = section;
    setTimeout(() => (saved = null), 2000);
  }

  async function onKinks(entries: Kink[]) {
    await putKinks(session.profileId!, entries);
    editing = null;
    await load();
    flash('kinks');
  }
  async function onToy(toy: { name: string; type: string; intiface_capable?: boolean } | null) {
    if (toy) await addToy(session.profileId!, toy);
    editing = null;
    await load();
    flash('toys');
  }
  async function onGoal(goal: { title: string; description?: string } | null) {
    if (goal) await addGoal(session.profileId!, goal);
    editing = null;
    await load();
    flash('goals');
  }
  async function onSo(ctx: { description?: string; values?: string; dynamic?: string }) {
    await putSoContext(session.profileId!, ctx);
    editing = null;
    await load();
    flash('so');
  }
  async function onPrefs(p: { intensity_ceiling: number; aftercare_prefs: string | null }) {
    await putPreferences(session.profileId!, p);
    editing = null;
    await load();
    flash('preferences');
  }

  // Merge the catalog vocabulary with any kinks the user already rated.
  const kinkRows = $derived(
    Array.from(new Set([...kinkVocab, ...(profile?.kinks.map((k) => k.kink) ?? [])]))
  );
  const kinkInitial = $derived(
    Object.fromEntries((profile?.kinks ?? []).map((k) => [k.kink, k.rating]))
  );
</script>

<SpokeHeader title="Sub Profile" />

{#if !profile}
  <p class="label pad">Loading…</p>
{:else}
  <div class="pad sections">
    <section>
      <h2 class="label">Character</h2>
      <p class="ledger"><span>{profile.character.honorific}</span> · calls you <span>{profile.character.address_term}</span></p>
    </section>

    <section>
      <h2 class="label">Archetype</h2>
      <ul class="ledger scores">
        {#each Object.entries(profile.archetype_scores) as [name, score]}
          <li>{name}: {score}</li>
        {/each}
      </ul>
    </section>

    <section>
      <div class="row">
        <h2 class="label">Limits {#if saved === 'kinks'}<span class="ok">saved</span>{/if}</h2>
        <button class="edit" onclick={openKinks}>Edit</button>
      </div>
      {#if editing === 'kinks'}
        <KinkSheet kinks={kinkRows} initial={kinkInitial} onnext={onKinks} />
      {:else}
        <ul class="kinks">
          {#each profile.kinks as k}
            <li class:hard={k.rating === 'hard_limit'} class:soft={k.rating === 'soft_limit'}>
              {k.kink.replaceAll('_', ' ')} · {k.rating.replace('_', ' ')}
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    <section>
      <div class="row">
        <h2 class="label">Toys {#if saved === 'toys'}<span class="ok">saved</span>{/if}</h2>
        <button class="edit" onclick={() => (editing = 'toys')}>Add</button>
      </div>
      {#if editing === 'toys'}
        <Toys onnext={onToy} />
      {:else}
        <ul class="list">{#each profile.toys as t}<li><span>{t.name}</span> · {t.type}</li>{/each}</ul>
      {/if}
    </section>

    <section>
      <div class="row">
        <h2 class="label">Goals {#if saved === 'goals'}<span class="ok">saved</span>{/if}</h2>
        <button class="edit" onclick={() => (editing = 'goals')}>Add</button>
      </div>
      {#if editing === 'goals'}
        <Goals onnext={onGoal} />
      {:else}
        <ul class="list">{#each profile.goals as g}<li>{g.title}</li>{/each}</ul>
      {/if}
    </section>

    <section>
      <div class="row">
        <h2 class="label">SO context {#if saved === 'so'}<span class="ok">saved</span>{/if}</h2>
        <button class="edit" onclick={() => (editing = 'so')}>Edit</button>
      </div>
      {#if editing === 'so'}
        <SoContext onnext={onSo} />
      {:else}
        <p>{profile.so_context?.description || '(none)'}</p>
      {/if}
    </section>

    <section>
      <div class="row">
        <h2 class="label">Preferences {#if saved === 'preferences'}<span class="ok">saved</span>{/if}</h2>
        <button class="edit" onclick={() => (editing = 'preferences')}>Edit</button>
      </div>
      {#if editing === 'preferences'}
        <Preferences
          onnext={onPrefs}
          initial={{ intensity_ceiling: profile.intensity_ceiling, aftercare_prefs: profile.aftercare_prefs }}
        />
      {:else}
        <p class="ledger">ceiling {profile.intensity_ceiling} · aftercare: {profile.aftercare_prefs || '—'}</p>
      {/if}
    </section>
  </div>
{/if}

<style>
  .pad {
    max-width: 720px;
    margin: 0 auto;
    padding: 24px 16px;
  }
  .sections {
    display: grid;
    gap: 28px;
  }
  .row {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .edit {
    font-family: var(--font-display);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    background: transparent;
    color: var(--paper);
    border: 1px solid var(--paper);
    padding: 6px 12px;
    cursor: pointer;
  }
  .ok {
    color: var(--accent);
    font-size: 0.7rem;
    margin-left: 8px;
  }
  .scores,
  .list,
  .kinks {
    list-style: none;
    padding: 0;
  }
  .kinks .hard {
    color: var(--accent);
  }
  .kinks .soft {
    color: var(--accent-muted);
  }
</style>
