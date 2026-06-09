import { api } from './client';

export interface Dossier {
  rank: string;
  merit: number;
  tokens: number;
  debt: number;
  disposition: { band: string; line: string; reason: string; standing: number };
  active_task: { description: string; status: string } | null;
  chastity: { locked: boolean; ends_at: string | null; seconds_remaining: number };
}

export const getDossier = (id: string) => api.get(`/api/profile/${id}/dossier`) as Promise<Dossier>;
