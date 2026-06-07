import { getDossier, type Dossier } from '$lib/api/dossier';
import { session } from './session.svelte';

class DossierStore {
  data = $state<Dossier | null>(null);

  async refresh() {
    const pid = session.profileId;
    if (!pid) return;
    this.data = await getDossier(pid);
  }
}

export const dossier = new DossierStore();
