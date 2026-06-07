const PHRASES = ['safeword', 'stop the scene', 'end the scene', 'i want to stop', 'i need to stop'];
const STANDALONE = ['red', "i'm done"];

// Mirrors the backend app/safety/detect.py. The chat input uses this to
// short-circuit a typed safeword to the deterministic stop BEFORE any chat call
// (Addendum A6 — the typed-phrase emergency exit).
export function isSafeword(text: string): boolean {
  const t = text.trim().toLowerCase();
  if (STANDALONE.includes(t)) return true;
  return PHRASES.some((p) => t.includes(p));
}
