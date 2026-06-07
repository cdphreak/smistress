import { api } from './client';

export interface Dossier {
  rank: string;
  merit: number;
  tokens: number;
  disposition: { band: string; line: string; reason: string; standing: number };
  active_task: { description: string; status: string } | null;
  denial_timers: number;
}

export const getDossier = (id: string) => api.get(`/api/profile/${id}/dossier`) as Promise<Dossier>;
