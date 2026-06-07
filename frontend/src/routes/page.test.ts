import { render, screen } from '@testing-library/svelte';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/chat', () => ({
  getMessages: vi.fn(async () => []),
  sendMessage: vi.fn(async (_id, content) => ({
    id: '2',
    role: 'assistant',
    content: 'Acknowledged.',
    created_at: 'now'
  }))
}));
vi.mock('$lib/api/dossier', () => ({
  getDossier: vi.fn(async () => ({
    rank: 'novice',
    merit: 0,
    tokens: 0,
    disposition: { band: 'cool', line: 'cool · exacting — no recent activity', reason: 'x', standing: 30 },
    active_task: null,
    denial_timers: 0
  }))
}));
// safety store hits the network on confirmStop; stub the api it calls
vi.mock('$lib/api/safety', () => ({
  safeword: vi.fn(async () => ({
    scene_halted: true,
    denial_lifted: 0,
    merit_penalty: 0,
    aftercare: 'rest',
    message: 'stopping'
  })),
  resume: vi.fn(),
  getSafety: vi.fn(async () => ({ is_halted: false, on_hiatus: false, consent_check_due: false }))
}));

import Page from './+page.svelte';
import { session } from '$lib/stores/session.svelte';
import { chat } from '$lib/stores/chat.svelte';

beforeEach(() => {
  session.setProfileId('p1');
  chat.messages = [];
});

test('shows the dossier and sends a message', async () => {
  render(Page);
  expect(await screen.findByText(/cool · exacting/)).toBeInTheDocument();

  const input = screen.getByPlaceholderText(/say something/i) as HTMLTextAreaElement;
  input.value = 'what now?';
  input.dispatchEvent(new Event('input', { bubbles: true }));
  screen.getByRole('button', { name: /send/i }).click();

  expect(await screen.findByText('Acknowledged.')).toBeInTheDocument();
});
