import { expect, test } from 'vitest';
import { isSafeword } from './phrases';

test('matches recognized safeword phrases and the standalone token', () => {
  expect(isSafeword('safeword')).toBe(true);
  expect(isSafeword('I want to stop')).toBe(true);
  expect(isSafeword('  RED  ')).toBe(true);
  expect(isSafeword('the red dress')).toBe(false);
  expect(isSafeword('what is my task?')).toBe(false);
});
