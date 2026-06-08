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
vi.mock('$lib/api/availability', () => ({
  getAvailability: vi.fn()
}));
vi.mock('$lib/api/drones', () => ({
  getStandingOrders: vi.fn(async () => ({
    notices: [{ unit: 'assignment', line: 'No standing assignment. Await Mistress.' }]
  }))
}));
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
import { availability } from '$lib/stores/availability.svelte';
import { drones } from '$lib/stores/drones.svelte';
import { getAvailability } from '$lib/api/availability';
import { ApiError } from '$lib/api/client';
import { sendMessage } from '$lib/api/chat';
import { getStandingOrders } from '$lib/api/drones';

beforeEach(() => {
  session.setProfileId('p1');
  chat.messages = [];
  availability.online = false;
  drones.notices = [];
  vi.clearAllMocks();
});

test('online: shows the dossier and sends a message', async () => {
  (getAvailability as ReturnType<typeof vi.fn>).mockResolvedValue({
    state: 'online',
    online: true,
    last_heartbeat_at: 'now'
  });
  render(Page);
  expect(await screen.findByText(/cool · exacting/)).toBeInTheDocument();

  const input = screen.getByPlaceholderText(/say something/i) as HTMLTextAreaElement;
  input.value = 'what now?';
  input.dispatchEvent(new Event('input', { bubbles: true }));
  screen.getByRole('button', { name: /send/i }).click();

  expect(await screen.findByText('Acknowledged.')).toBeInTheDocument();
});

test('offline: shows drone standing orders and no chat composer', async () => {
  (getAvailability as ReturnType<typeof vi.fn>).mockResolvedValue({
    state: 'offline',
    online: false,
    last_heartbeat_at: null
  });
  render(Page);
  expect(await screen.findByText(/an audience requires her presence/i)).toBeInTheDocument();
  expect(await screen.findByText(/no standing assignment/i)).toBeInTheDocument();
  // the live composer is not rendered when she is away
  expect(screen.queryByPlaceholderText(/say something/i)).toBeNull();
});

test('mid-session 503 flips the home to the offline drone surface', async () => {
  (getAvailability as ReturnType<typeof vi.fn>).mockResolvedValue({
    state: 'online',
    online: true,
    last_heartbeat_at: 'now'
  });
  (getStandingOrders as ReturnType<typeof vi.fn>).mockResolvedValue({
    notices: [{ unit: 'assignment', line: 'No standing assignment. Await Mistress.' }]
  });
  (sendMessage as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
    new ApiError(503, 'The Mistress is away — an audience requires her presence.')
  );
  render(Page);
  const input = (await screen.findByPlaceholderText(/say something/i)) as HTMLTextAreaElement;
  input.value = 'are you there?';
  input.dispatchEvent(new Event('input', { bubbles: true }));
  screen.getByRole('button', { name: /send/i }).click();

  // after the 503, the offline surface replaces the composer
  expect(await screen.findByText(/no standing assignment/i)).toBeInTheDocument();
  expect(screen.queryByPlaceholderText(/say something/i)).toBeNull();
});
