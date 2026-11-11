import { describe, it, expect } from 'vitest';
import { numberOperatorText, stringOperatorText } from '../operatorText';

describe('stringOperatorText', () => {
  it.each([
    ['exact', 'exactly matches'],
    ['exact_case_insensitive', 'exactly matches (case insensitive)'],
    ['not_equal', 'does not equal'],
    ['contains', 'contains'],
    ['contains_case_insensitive', 'contains (case insensitive)'],
    ['bogus', 'exactly matches'],
    [undefined, 'exactly matches'],
  ])('%s → %s', (op, text) => {
    expect(stringOperatorText(op)).toBe(text);
  });
});

describe('numberOperatorText', () => {
  it.each([
    ['equals', 'equals'],
    ['less_then', 'is less than'],
    ['greater_then', 'is greater than'],
    ['greater_or_equal_then', 'is greater than or equal to'],
    ['less_or_equal_then', 'is less than or equal to'],
    ['bogus', 'equals'],
    [undefined, 'equals'],
  ])('%s → %s', (op, text) => {
    expect(numberOperatorText(op)).toBe(text);
  });
});
