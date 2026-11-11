import { describe, it, expect } from 'vitest';
import { executionStatusType } from '../executionStatus';

describe('executionStatusType', () => {
  it.each([
    ['success', 'success'],
    ['failed', 'error'],
    ['error', 'error'],
    ['running', 'in-progress'],
    ['executing', 'in-progress'],
    ['pending', 'pending'],
    ['stopped', 'stopped'],
  ])('maps %s to %s', (status, expected) => {
    expect(executionStatusType(status)).toBe(expected);
  });

  it('renders unknown statuses as pending', () => {
    expect(executionStatusType('completed')).toBe('pending');
    expect(executionStatusType('')).toBe('pending');
  });
});
