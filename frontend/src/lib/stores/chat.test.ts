import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/chat', () => ({
  getMessages: vi.fn(async () => [{ id: '1', role: 'user', content: 'hi', created_at: 'now' }]),
  sendMessage: vi.fn(async (_id, content) => ({
    id: '2',
    role: 'assistant',
    content: `re: ${content}`,
    created_at: 'now'
  }))
}));

import { chat } from './chat.svelte';
import { session } from './session.svelte';

beforeEach(() => {
  session.setProfileId('p1');
  chat.messages = [];
});

test('load fetches history', async () => {
  await chat.load();
  expect(chat.messages.map((m) => m.content)).toEqual(['hi']);
});

test('send appends the user message then the reply', async () => {
  await chat.send('what now?');
  expect(chat.messages.map((m) => `${m.role}:${m.content}`)).toEqual([
    'user:what now?',
    'assistant:re: what now?'
  ]);
});
