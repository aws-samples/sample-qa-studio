/**
 * Pure helpers for the validation_type=date branch of validation/assertion
 * steps.
 *
 * For most date operators, validation_value is just a date string and
 * needs no special handling. For equals_within, the spec encodes
 * tolerance + unit + date as a JSON object inside validation_value:
 *
 *   {"date": "2024-01-02T15:00:00+00:00", "tolerance": 5, "unit": "minutes"}
 *
 * These helpers parse / serialize that payload so the editor can hold
 * its UI fields as plain strings while keeping the canonical JSON in
 * the existing validation_value field.
 */

export const VALIDATION_DATE_OPERATORS = [
  "before",
  "after",
  "equals",
  "not_equals",
  "equals_within",
] as const;

export type ValidationDateOperator = (typeof VALIDATION_DATE_OPERATORS)[number];

export const VALIDATION_DATE_OPERATOR_OPTIONS: ReadonlyArray<{
  label: string;
  value: ValidationDateOperator;
  description?: string;
}> = [
  { label: "Before", value: "before", description: "actual < expected" },
  { label: "After", value: "after", description: "actual > expected" },
  { label: "Equals", value: "equals", description: "actual == expected (millisecond precision)" },
  { label: "Not Equals", value: "not_equals", description: "actual != expected" },
  {
    label: "Equals Within (tolerance)",
    value: "equals_within",
    description: "abs(actual - expected) <= tolerance",
  },
];

export const VALIDATION_DATE_DURATION_UNITS = [
  "seconds",
  "minutes",
  "hours",
  "days",
  "weeks",
] as const;

export type ValidationDateDurationUnit = (typeof VALIDATION_DATE_DURATION_UNITS)[number];


export interface EqualsWithinFields {
  /** Date string to compare against. May be a {{ var }} reference. */
  date: string;
  /** Tolerance amount as a string (matches the Input field type). */
  tolerance: string;
  /** Duration unit. */
  unit: string;
}

export const EMPTY_EQUALS_WITHIN_FIELDS: EqualsWithinFields = {
  date: "",
  tolerance: "",
  unit: "",
};


/**
 * Parse the JSON payload inside validation_value for equals_within into
 * UI fields. Tolerates malformed input by returning empty fields — the
 * user can fix any blanks in the form, and the backend will reject
 * invalid input on save.
 */
export function loadEqualsWithinFields(validationValue: string): EqualsWithinFields {
  if (!validationValue) return { ...EMPTY_EQUALS_WITHIN_FIELDS };
  try {
    const parsed = JSON.parse(validationValue);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { ...EMPTY_EQUALS_WITHIN_FIELDS };
    }
    return {
      date: typeof parsed.date === "string" ? parsed.date : "",
      tolerance: parsed.tolerance != null ? String(parsed.tolerance) : "",
      unit: typeof parsed.unit === "string" ? parsed.unit : "",
    };
  } catch {
    return { ...EMPTY_EQUALS_WITHIN_FIELDS };
  }
}


/**
 * Serialize UI fields to the JSON payload expected in validation_value.
 *
 * Tolerance is parsed as a base-10 integer and falls back to 0 when
 * unparseable; the backend's pydantic model and the client validator
 * still reject invalid combinations on save.
 */
export function buildEqualsWithinValue(fields: EqualsWithinFields): string {
  const tolerance = parseInt(fields.tolerance, 10);
  return JSON.stringify({
    date: fields.date.trim(),
    tolerance: Number.isFinite(tolerance) ? tolerance : 0,
    unit: fields.unit || "minutes",
  });
}


/**
 * Pre-submit validity check for a date validation step.
 *
 * For non-equals_within operators, validation_value just needs to be a
 * non-empty string (date parsing happens server-side because the value
 * may be a {{ var }} reference). For equals_within, the JSON payload
 * must have a non-empty date, a valid duration unit, and a non-negative
 * integer tolerance.
 */
export function isDateValidationValid(operator: string, validationValue: string): boolean {
  if (operator === "equals_within") {
    const fields = loadEqualsWithinFields(validationValue);
    if (!fields.date.trim()) return false;
    if (!VALIDATION_DATE_DURATION_UNITS.includes(fields.unit as ValidationDateDurationUnit)) {
      return false;
    }
    const tolerance = parseInt(fields.tolerance, 10);
    return Number.isFinite(tolerance) && tolerance >= 0;
  }
  if (!VALIDATION_DATE_OPERATORS.includes(operator as ValidationDateOperator)) {
    return false;
  }
  return validationValue.trim().length > 0;
}
