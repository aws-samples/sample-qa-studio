import { describe, expect, it } from 'vitest';
import { getEffectiveBatchSize } from '../batchedPromiseAll';

describe('getEffectiveBatchSize', () => {
  it.each([1, 3, 5])('uses positive configured concurrency %s', (configured) => {
    expect(getEffectiveBatchSize(configured)).toBe(configured);
  });

  it.each([0, -1])('falls back to five for non-positive concurrency %s', (configured) => {
    expect(getEffectiveBatchSize(configured)).toBe(5);
  });
});
