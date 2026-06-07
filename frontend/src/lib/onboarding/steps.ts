export const STEPS = [
  'consent',
  'archetype',
  'kinks',
  'toys',
  'so',
  'goals',
  'character',
  'preferences',
  'reveal'
] as const;
export type Step = (typeof STEPS)[number];

export function stepIndex(step: string): number {
  return STEPS.indexOf(step as Step);
}
export function nextStep(step: Step): Step | null {
  const i = STEPS.indexOf(step);
  return i >= 0 && i < STEPS.length - 1 ? STEPS[i + 1] : null;
}
