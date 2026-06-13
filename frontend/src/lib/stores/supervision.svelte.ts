import {
  getSupervision,
  setMode as apiSetMode,
  setNote as apiSetNote,
  type SupervisionMode
} from '$lib/api/supervision';
import { session } from './session.svelte';

class SupervisionStore {
  mode = $state<SupervisionMode>('full');
  notes = $state<Record<string, string>>({});

  async refresh() {
    const pid = session.profileId;
    if (!pid) return;
    const s = await getSupervision(pid);
    this.mode = s.mode;
    this.notes = s.notes;
  }
  async setMode(mode: SupervisionMode) {
    const pid = session.profileId;
    if (!pid) return;
    const s = await apiSetMode(pid, mode);
    this.mode = s.mode;
    this.notes = s.notes;
  }
  async setNote(mode: SupervisionMode, note: string) {
    const pid = session.profileId;
    if (!pid) return;
    const s = await apiSetNote(pid, mode, note);
    this.mode = s.mode;
    this.notes = s.notes;
  }
}

export const supervision = new SupervisionStore();
