/**
 * Pure helpers for date transform-step argument shapes.
 *
 * These functions are testable in isolation (no React, no DOM) and form
 * the contract between the StepFormModal UI and the backend's
 * transform_args JSON shape. The backend args models live in
 * `web-app/worker/transform/date_ops.py` and the CLI mirror.
 *
 * Five operations:
 *   parse_date    { value, format? }
 *   format_date   { iso_value, format }
 *   add_duration  { iso_value, amount, unit }
 *   date_diff     { a, b, unit }
 *   to_epoch      { value, unit }
 */

export type DateOperation =
  | "parse_date"
  | "format_date"
  | "add_duration"
  | "date_diff"
  | "to_epoch";

export const DATE_OPERATIONS: ReadonlySet<DateOperation> = new Set([
  "parse_date",
  "format_date",
  "add_duration",
  "date_diff",
  "to_epoch",
]);

export const DURATION_UNITS = ["seconds", "minutes", "hours", "days", "weeks"] as const;
export type DurationUnit = (typeof DURATION_UNITS)[number];

export const EPOCH_UNITS = ["seconds", "millis"] as const;
export type EpochUnit = (typeof EPOCH_UNITS)[number];

export interface DateOpFields {
  /** Primary value input (used as `value`/`iso_value`/`a` depending on op). */
  primary: string;
  /** Secondary value input (only `date_diff` uses this — its `b` field). */
  secondary: string;
  /** strptime format string. Empty string means "auto-detect" for parse_date. */
  format: string;
  /** Signed integer amount for add_duration. */
  amount: string;
  /** Unit selector — duration units for add_duration/date_diff, epoch units for to_epoch. */
  unit: string;
}

export const EMPTY_DATE_FIELDS: DateOpFields = {
  primary: "",
  secondary: "",
  format: "",
  amount: "",
  unit: "",
};

/**
 * Build the transform_args object for a date operation from UI fields.
 *
 * Trims string inputs. Filters out empty optional fields (e.g. `format`
 * is omitted from `parse_date` args when empty so the backend
 * auto-detects). Throws nothing — invalid combinations produce
 * partially-populated args that the backend will reject with a clear
 * error, rather than failing client-side in a less informative way.
 */
export function buildDateOpArgs(
  operation: DateOperation,
  fields: DateOpFields,
): Record<string, unknown> {
  const primary = fields.primary.trim();
  const secondary = fields.secondary.trim();
  const format = fields.format.trim();

  switch (operation) {
    case "parse_date": {
      const args: Record<string, unknown> = { value: primary };
      if (format) args.format = format;
      return args;
    }
    case "format_date":
      return { iso_value: primary, format };
    case "add_duration": {
      const amount = parseInt(fields.amount, 10);
      return {
        iso_value: primary,
        amount: Number.isFinite(amount) ? amount : 0,
        unit: fields.unit || "days",
      };
    }
    case "date_diff":
      return {
        a: primary,
        b: secondary,
        unit: fields.unit || "days",
      };
    case "to_epoch":
      return {
        value: primary,
        unit: fields.unit || "seconds",
      };
  }
}

/**
 * Inverse of buildDateOpArgs: hydrate UI fields from a stored
 * transform_args object. Used when editing an existing step.
 *
 * Tolerates unknown shapes by falling back to empty strings —
 * the user can fix any blanks in the form, and the backend will
 * reject invalid input on save.
 */
export function loadDateOpFields(
  operation: DateOperation,
  args: Record<string, unknown> | null | undefined,
): DateOpFields {
  const safe = args ?? {};
  const str = (key: string): string => {
    const v = safe[key];
    return v == null ? "" : String(v);
  };

  switch (operation) {
    case "parse_date":
      return { ...EMPTY_DATE_FIELDS, primary: str("value"), format: str("format") };
    case "format_date":
      return { ...EMPTY_DATE_FIELDS, primary: str("iso_value"), format: str("format") };
    case "add_duration":
      return {
        ...EMPTY_DATE_FIELDS,
        primary: str("iso_value"),
        amount: str("amount"),
        unit: str("unit"),
      };
    case "date_diff":
      return {
        ...EMPTY_DATE_FIELDS,
        primary: str("a"),
        secondary: str("b"),
        unit: str("unit"),
      };
    case "to_epoch":
      return {
        ...EMPTY_DATE_FIELDS,
        primary: str("value"),
        unit: str("unit"),
      };
  }
}

/**
 * Pre-submit validity check for the date op fields.
 *
 * Mirrors the client-side validation in qa-studio-cli/qa_studio_cli/validation.py
 * but focused on the UI: "is the form complete enough to submit?". Date
 * string parsing happens server-side because the value may contain
 * `{{ var }}` references that only resolve at runtime.
 */
export function isDateOpValid(
  operation: DateOperation,
  fields: DateOpFields,
): boolean {
  const primary = fields.primary.trim();

  switch (operation) {
    case "parse_date":
      return primary.length > 0;
    case "format_date":
      return primary.length > 0 && fields.format.trim().length > 0;
    case "add_duration": {
      if (primary.length === 0) return false;
      if (!DURATION_UNITS.includes(fields.unit as DurationUnit)) return false;
      const amount = parseInt(fields.amount, 10);
      return Number.isFinite(amount);
    }
    case "date_diff":
      return (
        primary.length > 0 &&
        fields.secondary.trim().length > 0 &&
        DURATION_UNITS.includes(fields.unit as DurationUnit)
      );
    case "to_epoch":
      return primary.length > 0 && EPOCH_UNITS.includes(fields.unit as EpochUnit);
  }
}
