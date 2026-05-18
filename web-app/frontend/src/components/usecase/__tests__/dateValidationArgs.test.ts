/**
 * Unit tests for date validation argument helpers (Task 9).
 */

import { describe, it, expect } from "vitest";
import {
  VALIDATION_DATE_OPERATORS,
  VALIDATION_DATE_DURATION_UNITS,
  loadEqualsWithinFields,
  buildEqualsWithinValue,
  isDateValidationValid,
  EMPTY_EQUALS_WITHIN_FIELDS,
} from "../dateValidationArgs";


describe("VALIDATION_DATE_OPERATORS", () => {
  it("contains the five spec'd operators", () => {
    expect(new Set(VALIDATION_DATE_OPERATORS)).toEqual(
      new Set(["before", "after", "equals", "not_equals", "equals_within"]),
    );
  });
});


describe("loadEqualsWithinFields", () => {
  it("parses a valid JSON payload", () => {
    const value = JSON.stringify({
      date: "2024-01-02T15:00:00+00:00",
      tolerance: 5,
      unit: "minutes",
    });
    expect(loadEqualsWithinFields(value)).toEqual({
      date: "2024-01-02T15:00:00+00:00",
      tolerance: "5",
      unit: "minutes",
    });
  });

  it("returns empty fields for empty input", () => {
    expect(loadEqualsWithinFields("")).toEqual(EMPTY_EQUALS_WITHIN_FIELDS);
  });

  it("returns empty fields for malformed JSON", () => {
    expect(loadEqualsWithinFields("not-json{{{")).toEqual(EMPTY_EQUALS_WITHIN_FIELDS);
  });

  it("returns empty fields for top-level array", () => {
    expect(loadEqualsWithinFields(JSON.stringify(["x"]))).toEqual(EMPTY_EQUALS_WITHIN_FIELDS);
  });

  it("returns empty fields for top-level null", () => {
    expect(loadEqualsWithinFields("null")).toEqual(EMPTY_EQUALS_WITHIN_FIELDS);
  });

  it("returns blanks for missing fields, full values for present", () => {
    expect(
      loadEqualsWithinFields(JSON.stringify({ date: "2024-01-02" })),
    ).toEqual({ date: "2024-01-02", tolerance: "", unit: "" });
  });

  it("coerces non-string date to empty", () => {
    expect(
      loadEqualsWithinFields(JSON.stringify({ date: 12345, tolerance: 1, unit: "minutes" })),
    ).toEqual({ date: "", tolerance: "1", unit: "minutes" });
  });
});


describe("buildEqualsWithinValue", () => {
  it("serializes the payload as JSON with parsed integer tolerance", () => {
    const out = buildEqualsWithinValue({
      date: "2024-01-02",
      tolerance: "5",
      unit: "minutes",
    });
    expect(JSON.parse(out)).toEqual({
      date: "2024-01-02",
      tolerance: 5,
      unit: "minutes",
    });
  });

  it("trims whitespace on the date", () => {
    const out = buildEqualsWithinValue({
      date: "  2024-01-02  ",
      tolerance: "5",
      unit: "minutes",
    });
    expect(JSON.parse(out).date).toBe("2024-01-02");
  });

  it("falls back to tolerance=0 for unparseable input", () => {
    const out = buildEqualsWithinValue({
      date: "2024-01-02",
      tolerance: "abc",
      unit: "minutes",
    });
    expect(JSON.parse(out).tolerance).toBe(0);
  });

  it("defaults unit to 'minutes' when empty", () => {
    const out = buildEqualsWithinValue({
      date: "2024-01-02",
      tolerance: "5",
      unit: "",
    });
    expect(JSON.parse(out).unit).toBe("minutes");
  });

  it("preserves negative tolerance for the validator to reject downstream", () => {
    // We don't reject in build (the user's typing); we let isDateValidationValid
    // and the backend validator reject it.
    const out = buildEqualsWithinValue({
      date: "2024-01-02",
      tolerance: "-5",
      unit: "minutes",
    });
    expect(JSON.parse(out).tolerance).toBe(-5);
  });

  it("round-trips through load → build → load", () => {
    const initial = JSON.stringify({
      date: "2024-01-02T15:00:00+00:00",
      tolerance: 30,
      unit: "seconds",
    });
    const fields = loadEqualsWithinFields(initial);
    const rebuilt = buildEqualsWithinValue(fields);
    expect(loadEqualsWithinFields(rebuilt)).toEqual(fields);
  });
});


describe("isDateValidationValid", () => {
  describe("non-equals_within operators", () => {
    it.each(["before", "after", "equals", "not_equals"])(
      "operator '%s' requires non-empty validation_value",
      (op) => {
        expect(isDateValidationValid(op, "2024-01-02")).toBe(true);
        expect(isDateValidationValid(op, "")).toBe(false);
        expect(isDateValidationValid(op, "   ")).toBe(false);
      },
    );

    it("accepts {{ var }} references", () => {
      expect(isDateValidationValid("equals", "{{ baseline_date }}")).toBe(true);
    });
  });

  describe("unknown operator", () => {
    it("rejects an operator not in the supported set", () => {
      expect(isDateValidationValid("between", "2024-01-02")).toBe(false);
    });
  });

  describe("equals_within", () => {
    const valid = JSON.stringify({
      date: "2024-01-02",
      tolerance: 5,
      unit: "minutes",
    });

    it("accepts a fully-populated payload", () => {
      expect(isDateValidationValid("equals_within", valid)).toBe(true);
    });

    it("accepts zero tolerance", () => {
      const v = JSON.stringify({ date: "2024-01-02", tolerance: 0, unit: "seconds" });
      expect(isDateValidationValid("equals_within", v)).toBe(true);
    });

    it("rejects an empty validation_value", () => {
      expect(isDateValidationValid("equals_within", "")).toBe(false);
    });

    it("rejects malformed JSON", () => {
      expect(isDateValidationValid("equals_within", "not-json")).toBe(false);
    });

    it("rejects missing date", () => {
      const v = JSON.stringify({ tolerance: 5, unit: "minutes" });
      expect(isDateValidationValid("equals_within", v)).toBe(false);
    });

    it("rejects missing unit", () => {
      const v = JSON.stringify({ date: "2024-01-02", tolerance: 5 });
      expect(isDateValidationValid("equals_within", v)).toBe(false);
    });

    it("rejects unsupported unit", () => {
      const v = JSON.stringify({ date: "2024-01-02", tolerance: 5, unit: "months" });
      expect(isDateValidationValid("equals_within", v)).toBe(false);
    });

    it("rejects negative tolerance", () => {
      const v = JSON.stringify({ date: "2024-01-02", tolerance: -1, unit: "minutes" });
      expect(isDateValidationValid("equals_within", v)).toBe(false);
    });

    it("rejects non-integer tolerance encoded as string", () => {
      // load returns "abc" for tolerance, which parseInt -> NaN
      const v = JSON.stringify({ date: "2024-01-02", tolerance: "abc", unit: "minutes" });
      expect(isDateValidationValid("equals_within", v)).toBe(false);
    });

    it.each(VALIDATION_DATE_DURATION_UNITS)("accepts unit '%s'", (unit) => {
      const v = JSON.stringify({ date: "2024-01-02", tolerance: 1, unit });
      expect(isDateValidationValid("equals_within", v)).toBe(true);
    });
  });
});
