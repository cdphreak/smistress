import { getAvailability } from '$lib/api/availability';

// System-wide presence of the home-box LLM (Addendum B2). The home surface
// switches on this: online -> live chat; offline -> the drone standing-orders.
class Availability {
  online = $state(false);

  async refresh() {
    try {
      this.online = (await getAvailability()).online;
    } catch {
      this.online = false; // unreachable backend reads as offline
    }
  }

  setOffline() {
    this.online = false;
  }
}

export const availability = new Availability();
