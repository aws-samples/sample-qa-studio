import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { formatTimeAgo } from '../time';

const NOW = new Date('2026-03-10T12:00:00Z');
const ago = (ms: number) => new Date(NOW.getTime() - ms).toISOString();
const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

describe('formatTimeAgo', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it.each([
    [0, 'just now'],
    [59_999, 'just now'],
    [MIN, '1m ago'],
    [59 * MIN, '59m ago'],
    [HOUR, '1h ago'],
    [23 * HOUR + 59 * MIN, '23h ago'],
    [DAY, '1d ago'],
    [6 * DAY + 23 * HOUR, '6d ago'],
  ])('%i ms ago → %s', (ms, expected) => {
    expect(formatTimeAgo(ago(ms))).toBe(expected);
  });

  it('shows the locale date from 7 days on', () => {
    const past = ago(7 * DAY);
    expect(formatTimeAgo(past)).toBe(new Date(past).toLocaleDateString());
  });

  it('falls through to "Invalid Date" for an unparseable timestamp', () => {
    expect(formatTimeAgo('not a date')).toBe('Invalid Date');
  });
});
