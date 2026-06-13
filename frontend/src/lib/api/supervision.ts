import { api } from './client';

export type SupervisionMode = 'full' | 'discreet' | 'task' | 'homeoffice' | 'vacation';

export interface Supervision {
  mode: SupervisionMode;
  notes: Record<string, string>;
}

export const getSupervision = (id: string) =>
  api.get(`/api/profile/${id}/supervision`) as Promise<Supervision>;
export const setMode = (id: string, mode: SupervisionMode) =>
  api.put(`/api/profile/${id}/supervision/mode`, { mode }) as Promise<Supervision>;
export const setNote = (id: string, mode: SupervisionMode, note: string) =>
  api.put(`/api/profile/${id}/supervision/note`, { mode, note }) as Promise<Supervision>;
