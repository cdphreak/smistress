import { getStandingOrders, type DroneNotice } from '$lib/api/drones';
import { session } from './session.svelte';

class Drones {
  notices = $state<DroneNotice[]>([]);

  async refresh() {
    const pid = session.profileId;
    if (!pid) return;
    this.notices = (await getStandingOrders(pid)).notices;
  }
}

export const drones = new Drones();
