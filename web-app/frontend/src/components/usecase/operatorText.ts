/**
 * Human-readable comparison operators of validation / assertion steps
 * (stored values such as `exact`, `less_then`). Unknown or missing
 * operators fall back to the default operator of the type.
 */

export function stringOperatorText(op?: string): string {
  switch (op) {
    case 'exact': return 'exactly matches';
    case 'exact_case_insensitive': return 'exactly matches (case insensitive)';
    case 'not_equal': return 'does not equal';
    case 'contains': return 'contains';
    case 'contains_case_insensitive': return 'contains (case insensitive)';
    default: return 'exactly matches';
  }
}

export function numberOperatorText(op?: string): string {
  switch (op) {
    case 'equals': return 'equals';
    case 'less_then': return 'is less than';
    case 'greater_then': return 'is greater than';
    case 'greater_or_equal_then': return 'is greater than or equal to';
    case 'less_or_equal_then': return 'is less than or equal to';
    default: return 'equals';
  }
}
