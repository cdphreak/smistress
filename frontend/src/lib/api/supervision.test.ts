import { afterEach, expect, test, vi } from 'vitest';

vi.mock('./client', () => ({
  api: { get: vi.fn(), put: vi.fn() }
}));

import { api } from './client';
import { getSupervision, setMode, setNote } from './supervision';

afterEach(() => vi.clearAllMocks());

test('getSupervision GETs the supervision resource', () => {
  getSupervision('p1');
  expect(api.get).toHaveBeenCalledWith('/api/profile/p1/supervision');
});

test('setMode PUTs the chosen mode', () => {
  setMode('p1', 'discreet');
  expect(api.put).toHaveBeenCalledWith('/api/profile/p1/supervision/mode', { mode: 'discreet' });
});

test('setNote PUTs the mode + note', () => {
  setNote('p1', 'task', 'be quick');
  expect(api.put).toHaveBeenCalledWith('/api/profile/p1/supervision/note', {
    mode: 'task',
    note: 'be quick'
  });
});
