import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('$lib/api/supervision', () => ({
  getSupervision: vi.fn(async () => ({ mode: 'discreet', notes: { discreet: 'hi' } })),
  setMode: vi.fn(async () => ({ mode: 'discreet', notes: { discreet: 'hi' } })),
  setNote: vi.fn(async () => ({ mode: 'task', notes: { task: 'be quick' } }))
}));

import { supervision } from './supervision.svelte';
import { session } from './session.svelte';

beforeEach(() => {
  localStorage.clear();
  session.setProfileId('p1');
  supervision.mode = 'full';
  supervision.notes = {};
});

test('refresh() calls getSupervision and stores mode + notes', async () => {
  const api = await import('$lib/api/supervision');
  await supervision.refresh();
  expect(api.getSupervision).toHaveBeenCalledWith('p1');
  expect(supervision.mode).toBe('discreet');
  expect(supervision.notes).toEqual({ discreet: 'hi' });
});

test('setMode() calls api setMode and updates mode', async () => {
  const { setMode: apiSetMode } = await import('$lib/api/supervision');
  await supervision.setMode('discreet');
  expect(apiSetMode).toHaveBeenCalledWith('p1', 'discreet');
  expect(supervision.mode).toBe('discreet');
  expect(supervision.notes).toEqual({ discreet: 'hi' });
});

test('setNote() calls api setNote and updates notes', async () => {
  const { setNote: apiSetNote } = await import('$lib/api/supervision');
  await supervision.setNote('task', 'be quick');
  expect(apiSetNote).toHaveBeenCalledWith('p1', 'task', 'be quick');
  expect(supervision.mode).toBe('task');
  expect(supervision.notes).toEqual({ task: 'be quick' });
});

test('refresh() does not call api when session.profileId is null', async () => {
  const api = await import('$lib/api/supervision');
  vi.clearAllMocks();
  session.clear();
  await supervision.refresh();
  expect(api.getSupervision).not.toHaveBeenCalled();
});
