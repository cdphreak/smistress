import { api } from './client';

export type KinkRating = 'favorite' | 'like' | 'curious' | 'soft_limit' | 'hard_limit' | 'na';

export const submitArchetype = (id: string, answers: Record<string, number>) =>
  api.post(`/api/profile/${id}/archetype`, { answers });
export const putKinks = (id: string, entries: { kink: string; rating: KinkRating }[]) =>
  api.put(`/api/profile/${id}/kinks`, { entries });
export const addToy = (
  id: string,
  toy: { name: string; type: string; intiface_capable?: boolean; notes?: string }
) => api.post(`/api/profile/${id}/toys`, toy);
export const addGoal = (id: string, goal: { title: string; description?: string }) =>
  api.post(`/api/profile/${id}/goals`, goal);
export const putSoContext = (
  id: string,
  ctx: { description?: string; values?: string; dynamic?: string }
) => api.put(`/api/profile/${id}/so-context`, ctx);
export const putCharacter = (id: string, patch: Record<string, unknown>) =>
  api.put(`/api/profile/${id}/character`, patch);
export const getCharacter = (id: string) => api.get(`/api/profile/${id}/character`);
export const putPreferences = (
  id: string,
  prefs: { intensity_ceiling: number; aftercare_prefs?: string | null }
) => api.put(`/api/profile/${id}/preferences`, prefs);
export const getProfile = (id: string) => api.get(`/api/profile/${id}`);
