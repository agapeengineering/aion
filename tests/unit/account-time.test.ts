import { it, expect, vi } from 'vitest';
import { verificationDeadline } from '../../apps/web/src/account-time';

it('uses a relative monotonic lifetime despite fast, slow or changing device clocks', () => {
  const wall = vi.spyOn(Date, 'now');
  try {
    for (const skew of [-3600000, 0, 3600000]) {
      wall.mockReturnValue(1800000000000 + skew);
      const received = 12345,
        deadline = verificationDeadline(599, received);
      expect(deadline - received).toBe(599000);
      expect(deadline > received + 598999).toBe(true);
      expect(deadline > received + 599000).toBe(false);
    }
    expect(wall).not.toHaveBeenCalled();
  } finally {
    wall.mockRestore();
  }
});
it('does not unlock confirmation for absent, exhausted or malformed server lifetimes', () => {
  for (const seconds of [0, -1, NaN, Infinity, 601])
    expect(verificationDeadline(seconds, 100)).toBe(0);
});
