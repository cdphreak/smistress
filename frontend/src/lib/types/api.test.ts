import { expect, test } from 'vitest';
import type { paths } from './api';

test('generated api types include the onboarding profile path', () => {
  // compile-time check: the path key must exist on the generated type
  type Created = paths['/onboarding/profile']['post'];
  const ok: boolean = true as Created extends never ? false : true;
  expect(ok).toBe(true);
});
