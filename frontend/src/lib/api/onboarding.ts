import { api } from './client';

export interface Questionnaire {
  statements: { id: string; archetype: string; text: string }[];
  kinks: string[];
  toy_types: string[];
  answer_scale: { min: number; max: number };
}
export interface ProfileCreated {
  id: string;
  intensity_ceiling: number;
}

export const getQuestionnaire = () =>
  api.get('/api/onboarding/questionnaire') as Promise<Questionnaire>;
export const createProfile = (consent: { is_adult: boolean; consent_acknowledged: boolean }) =>
  api.post('/api/onboarding/profile', consent) as Promise<ProfileCreated>;
