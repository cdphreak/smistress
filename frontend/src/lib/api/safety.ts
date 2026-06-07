import { api } from './client';
import type { KinkRating } from './profile';

export interface StopReceipt {
  scene_halted: boolean;
  denial_lifted: number;
  merit_penalty: number;
  aftercare: string;
  message: string;
}
export interface SafetyState {
  is_halted: boolean;
  on_hiatus: boolean;
  consent_check_due: boolean;
}

export const safeword = (id: string) =>
  api.post(`/api/profile/${id}/safeword`) as Promise<StopReceipt>;
export const resume = (id: string) =>
  api.post(`/api/profile/${id}/resume`) as Promise<SafetyState>;
export const getSafety = (id: string) =>
  api.get(`/api/profile/${id}/safety`) as Promise<SafetyState>;
export const setHiatus = (id: string, on: boolean) =>
  api.post(`/api/profile/${id}/hiatus`, { on }) as Promise<SafetyState>;
export const lowerLimit = (id: string, kink: string, rating: KinkRating) =>
  api.post(`/api/profile/${id}/lower-limit`, { kink, rating }) as Promise<{
    kink: string;
    rating: KinkRating;
  }>;
export const consentCheck = (id: string) =>
  api.post(`/api/profile/${id}/consent-check`) as Promise<SafetyState>;
export const deleteProfile = (id: string) => api.del(`/api/profile/${id}`);
