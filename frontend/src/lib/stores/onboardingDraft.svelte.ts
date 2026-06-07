const KEY = 'smistress.onboarding';

type Draft = Record<string, unknown>;

function load(): Draft {
  if (typeof localStorage === 'undefined') return {};
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '{}');
  } catch {
    return {};
  }
}

class OnboardingDraft {
  data = $state<Draft>(load());

  get(step: string): unknown {
    return this.data[step];
  }
  set(step: string, value: unknown) {
    this.data = { ...this.data, [step]: value };
    if (typeof localStorage !== 'undefined') localStorage.setItem(KEY, JSON.stringify(this.data));
  }
  clear() {
    this.data = {};
    if (typeof localStorage !== 'undefined') localStorage.removeItem(KEY);
  }
}

export const onboardingDraft = new OnboardingDraft();
