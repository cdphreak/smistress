import type { Page } from '@playwright/test';

// Minimal in-memory backend stub. Routes are matched by method + path suffix.
export async function mockApi(page: Page) {
  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname; // e.g. /api/onboarding/profile
    const method = req.method();
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (path.endsWith('/api/onboarding/questionnaire') && method === 'GET') {
      return json({
        statements: [
          { id: 'q1', archetype: 'submissive', text: 'I want to be told what to do.' },
          { id: 'q2', archetype: 'slave', text: 'I want to surrender control.' }
        ],
        kinks: ['bondage', 'spanking'],
        toy_types: ['vibrator', 'chastity_cage', 'collar'],
        answer_scale: { min: 0, max: 4 }
      });
    }
    if (path.endsWith('/api/onboarding/profile') && method === 'POST') {
      return json({ id: 'e2e-profile', intensity_ceiling: 50 }, 201);
    }
    if (path.includes('/archetype') && method === 'POST') return json({ scores: { submissive: 80 } });
    if (path.endsWith('/kinks') && method === 'PUT') return json({ count: 1 });
    if (path.endsWith('/toys') && method === 'POST') return json({ name: 'x', type: 'y' }, 201);
    if (path.endsWith('/goals') && method === 'POST') return json({ title: 'g', description: '', status: 'active' }, 201);
    if (path.endsWith('/so-context') && method === 'PUT') return json({ description: '', values: null, dynamic: null });
    if (path.endsWith('/character') && method === 'GET') return json(CHARACTER);
    if (path.endsWith('/character') && method === 'PUT') return json(CHARACTER);
    if (path.endsWith('/preferences') && method === 'PUT') return json({ intensity_ceiling: 50, aftercare_prefs: null });
    if (path.endsWith('/safeword') && method === 'POST')
      return json({ scene_halted: true, denial_lifted: 0, merit_penalty: 0, aftercare: 'rest a while', message: "Okay — we're stopping now." });
    if (path.endsWith('/resume') && method === 'POST') return json(SAFE_OK);
    if (path.endsWith('/safety') && method === 'GET') return json(SAFE_OK);
    if (path.endsWith('/hiatus') && method === 'POST') return json({ ...SAFE_OK, on_hiatus: true });
    if (path.endsWith('/api/llm/availability') && method === 'GET')
      return json({ state: 'online', online: true, last_heartbeat_at: 'now' });
    if (path.endsWith('/standing-orders') && method === 'GET')
      return json({ notices: [{ unit: 'assignment', line: 'No standing assignment. Await Mistress.' }] });
    if (path.endsWith('/messages') && method === 'GET') return json([]);
    if (path.endsWith('/chat') && method === 'POST') {
      const body = req.postDataJSON() as { content: string };
      const wantsTask = /task/i.test(body.content);
      return json({
        id: 'm2',
        role: 'assistant',
        content: `Heard: ${body.content}`,
        action: wantsTask
          ? { tool: 'assign_task', description: 'Posture drill', proof: 'honor', merit_reward: 10 }
          : null,
        created_at: 'now'
      });
    }
    if (path.endsWith('/dossier') && method === 'GET')
      return json({
        rank: 'novice', merit: 0, tokens: 0,
        disposition: { band: 'cool', line: 'cool · exacting — no recent activity', reason: 'x', standing: 30 },
        active_task: null, denial_timers: 0
      });
    // assembled profile GET (path ends with the bare profile id)
    if (/\/api\/profile\/[^/]+$/.test(path) && method === 'GET') return json(PROFILE);
    return json({}, 200);
  });
}

const CHARACTER = {
  name: null, honorific: 'Headmistress', address_term: 'student', pronouns: 'she/her',
  archetype_blend: { governess: 70, drill_instructor: 30 },
  warmth: 40, strictness: 80, sadism: 30, formality: 70, verbosity: 50, crudeness: 30, wit: 75,
  signature_flavor: null
};
const SAFE_OK = { is_halted: false, on_hiatus: false, consent_check_due: false };
const PROFILE = {
  id: 'e2e-profile', intensity_ceiling: 50, aftercare_prefs: 'tea',
  archetype_scores: { submissive: 80, slave: 20 },
  kinks: [{ kink: 'bondage', rating: 'favorite' }],
  toys: [{ name: 'Apex', type: 'vibrator' }],
  goals: [{ title: 'Posture', description: '', status: 'active' }],
  so_context: { description: 'my partner', values: null, dynamic: null },
  character: CHARACTER
};
