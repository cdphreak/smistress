import { api } from './client';

export interface Availability {
  state: string;
  online: boolean;
  last_heartbeat_at: string | null;
}

// System-wide (single-user); not scoped to a profile.
export const getAvailability = () => api.get('/api/llm/availability') as Promise<Availability>;
