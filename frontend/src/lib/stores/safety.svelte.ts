import { getSafety, resume as apiResume, safeword, type StopReceipt } from '$lib/api/safety';
import { session } from './session.svelte';

// Global, deterministic safety state (Addendum A6). The pre-halt is pure client
// state set the instant the SAFE sheet opens — before any network call.
class Safety {
  paused = $state(false); // client pre-halt OR server-confirmed halt
  isHalted = $state(false); // server-confirmed (after POST /safeword)
  onHiatus = $state(false);
  receipt = $state<StopReceipt | null>(null);

  preHalt() {
    this.paused = true;
  }
  cancelPreHalt() {
    // Only un-pause if the server hasn't confirmed a full stop.
    if (!this.isHalted) this.paused = false;
  }
  async confirmStop() {
    const pid = session.profileId;
    if (!pid) return;
    this.receipt = await safeword(pid);
    this.isHalted = true;
    this.paused = true;
  }
  async refresh() {
    const pid = session.profileId;
    if (!pid) return;
    const s = await getSafety(pid);
    this.isHalted = s.is_halted;
    this.onHiatus = s.on_hiatus;
    this.paused = s.is_halted;
  }
  async resumeScene() {
    const pid = session.profileId;
    if (!pid) return;
    const s = await apiResume(pid);
    this.isHalted = s.is_halted;
    this.paused = false;
    this.receipt = null;
  }
}

export const safety = new Safety();
