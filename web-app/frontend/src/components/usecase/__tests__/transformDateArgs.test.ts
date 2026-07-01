/**
 * Unit tests for date transform argument helpers (Task 8).
 *
 * These functions form the contract between the StepFormModal UI and the
 * backend's transform_args JSON shape. Keeping them as pure functions
 * lets us test the serialization/hydration round-trip without rendering
 * the (massive) StepFormModal component.
 */

import { describe, it, expect } from "vitest";
import {
  buildDateOpArgs,
  loadDateOpFields,
  isDateOpValid,
  EMPTY_DATE_FIELDS,
  DATE_OPERATIONS,
  DURATION_UNITS,
  EPOCH_UNITS,
  type DateOpFields,
} from "../transformDateArgs";


function fields(overrides: Partial<DateOpFields> = {}): DateOpFields {
  return { ...EMPTY_DATE_FIELDS, ...overrides };
}


describe("DATE_OPERATIONS set", () => {
  it("contains exactly the five v1 date operations", () => {
    expect(new Set(DATE_OPERATIONS)).toEqual(
      new Set(["parse_date", "format_date", "add_duration", "date_diff", "to_epoch"]),
    );
  });
});


describe("buildDateOpArgs", () => {
  describe("parse_date", () => {
    it("returns just value when format is empty (auto-detect)", () => {
      const args = buildDateOpArgs("parse_date", fields({ primary: "2024-01-02" }));
      expect(args).toEqual({ value: "2024-01-02" });
    });

    it("includes format when provided", () => {
      const args = buildDateOpArgs("parse_date", fields({
        primary: "02/01/2024",
        format: "%d/%m/%Y",
      }));
      expect(args).toEqual({ value: "02/01/2024", format: "%d/%m/%Y" });
    });

    it("trims whitespace on value", () => {
      const args = buildDateOpArgs("parse_date", fields({ primary: "  2024-01-02  " }));
      expect(args).toEqual({ value: "2024-01-02" });
    });

    it("trims whitespace on format", () => {
      const args = buildDateOpArgs("parse_date", fields({
        primary: "02/01/2024",
        format: "  %d/%m/%Y  ",
      }));
      expect(args).toEqual({ value: "02/01/2024", format: "%d/%m/%Y" });
    });
  });

  describe("format_date", () => {
    it("includes both iso_value and format", () => {
      const args = buildDateOpArgs("format_date", fields({
        primary: "2024-01-02T00:00:00+00:00",
        format: "%d/%m/%Y",
      }));
      expect(args).toEqual({
        iso_value: "2024-01-02T00:00:00+00:00",
        format: "%d/%m/%Y",
      });
    });
  });

  describe("add_duration", () => {
    it("parses amount as integer", () => {
      const args = buildDateOpArgs("add_duration", fields({
        primary: "2024-01-02",
        amount: "30",
        unit: "days",
      }));
      expect(args).toEqual({ iso_value: "2024-01-02", amount: 30, unit: "days" });
    });

    it("supports negative amounts", () => {
      const args = buildDateOpArgs("add_duration", fields({
        primary: "2024-01-05",
        amount: "-3",
        unit: "days",
      }));
      expect(args).toEqual({ iso_value: "2024-01-05", amount: -3, unit: "days" });
    });

    it("falls back to amount=0 when unparseable", () => {
      const args = buildDateOpArgs("add_duration", fields({
        primary: "2024-01-02",
        amount: "not-a-number",
        unit: "days",
      }));
      expect(args.amount).toBe(0);
    });

    it("defaults unit to 'days' when empty", () => {
      const args = buildDateOpArgs("add_duration", fields({
        primary: "2024-01-02",
        amount: "5",
      }));
      expect(args.unit).toBe("days");
    });
  });

  describe("date_diff", () => {
    it("uses 'a' and 'b' as keys, not 'value'", () => {
      const args = buildDateOpArgs("date_diff", fields({
        primary: "2024-01-05",
        secondary: "2024-01-02",
        unit: "days",
      }));
      expect(args).toEqual({ a: "2024-01-05", b: "2024-01-02", unit: "days" });
    });
  });

  describe("to_epoch", () => {
    it("produces value + unit", () => {
      const args = buildDateOpArgs("to_epoch", fields({
        primary: "2024-01-02",
        unit: "millis",
      }));
      expect(args).toEqual({ value: "2024-01-02", unit: "millis" });
    });

    it("defaults unit to 'seconds'", () => {
      const args = buildDateOpArgs("to_epoch", fields({ primary: "2024-01-02" }));
      expect(args.unit).toBe("seconds");
    });
  });
});


describe("loadDateOpFields (round-trip)", () => {
  it("parse_date round-trips with format", () => {
    const original = fields({ primary: "02/01/2024", format: "%d/%m/%Y" });
    const args = buildDateOpArgs("parse_date", original);
    const loaded = loadDateOpFields("parse_date", args);
    expect(loaded.primary).toBe("02/01/2024");
    expect(loaded.format).toBe("%d/%m/%Y");
  });

  it("parse_date round-trips without format (auto-detect)", () => {
    const args = buildDateOpArgs("parse_date", fields({ primary: "2024-01-02" }));
    const loaded = loadDateOpFields("parse_date", args);
    expect(loaded.primary).toBe("2024-01-02");
    expect(loaded.format).toBe("");
  });

  it("format_date round-trips", () => {
    const args = buildDateOpArgs("format_date", fields({
      primary: "2024-01-02T00:00:00+00:00",
      format: "%d/%m/%Y",
    }));
    const loaded = loadDateOpFields("format_date", args);
    expect(loaded.primary).toBe("2024-01-02T00:00:00+00:00");
    expect(loaded.format).toBe("%d/%m/%Y");
  });

  it("add_duration round-trips with negative amount", () => {
    const args = buildDateOpArgs("add_duration", fields({
      primary: "2024-01-02", amount: "-7", unit: "days",
    }));
    const loaded = loadDateOpFields("add_duration", args);
    expect(loaded.primary).toBe("2024-01-02");
    expect(loaded.amount).toBe("-7");
    expect(loaded.unit).toBe("days");
  });

  it("date_diff round-trips both values", () => {
    const args = buildDateOpArgs("date_diff", fields({
      primary: "2024-01-05", secondary: "2024-01-02", unit: "weeks",
    }));
    const loaded = loadDateOpFields("date_diff", args);
    expect(loaded.primary).toBe("2024-01-05");
    expect(loaded.secondary).toBe("2024-01-02");
    expect(loaded.unit).toBe("weeks");
  });

  it("to_epoch round-trips", () => {
    const args = buildDateOpArgs("to_epoch", fields({
      primary: "2024-01-02", unit: "millis",
    }));
    const loaded = loadDateOpFields("to_epoch", args);
    expect(loaded.primary).toBe("2024-01-02");
    expect(loaded.unit).toBe("millis");
  });

  it("tolerates null args by returning empty fields", () => {
    const loaded = loadDateOpFields("parse_date", null);
    expect(loaded).toEqual(EMPTY_DATE_FIELDS);
  });

  it("tolerates undefined args by returning empty fields", () => {
    const loaded = loadDateOpFields("date_diff", undefined);
    expect(loaded).toEqual(EMPTY_DATE_FIELDS);
  });

  it("tolerates missing keys by returning empty strings for missing fields", () => {
    const loaded = loadDateOpFields("parse_date", {});
    expect(loaded.primary).toBe("");
    expect(loaded.format).toBe("");
  });
});


describe("isDateOpValid", () => {
  describe("parse_date", () => {
    it("requires non-empty primary value", () => {
      expect(isDateOpValid("parse_date", fields({ primary: "2024-01-02" }))).toBe(true);
      expect(isDateOpValid("parse_date", fields({ primary: "" }))).toBe(false);
      expect(isDateOpValid("parse_date", fields({ primary: "   " }))).toBe(false);
    });

    it("accepts {{ var }} references in primary", () => {
      expect(isDateOpValid("parse_date", fields({ primary: "{{ order_date }}" }))).toBe(true);
    });

    it("does not require format (auto-detect)", () => {
      expect(isDateOpValid("parse_date", fields({ primary: "2024-01-02" }))).toBe(true);
    });
  });

  describe("format_date", () => {
    it("requires both primary and format", () => {
      expect(isDateOpValid("format_date", fields({
        primary: "2024-01-02", format: "%d/%m/%Y",
      }))).toBe(true);
      expect(isDateOpValid("format_date", fields({ primary: "2024-01-02" }))).toBe(false);
      expect(isDateOpValid("format_date", fields({ format: "%d/%m/%Y" }))).toBe(false);
    });
  });

  describe("add_duration", () => {
    it("requires primary, amount, and a valid unit", () => {
      expect(isDateOpValid("add_duration", fields({
        primary: "2024-01-02", amount: "5", unit: "days",
      }))).toBe(true);
    });

    it("rejects empty amount", () => {
      expect(isDateOpValid("add_duration", fields({
        primary: "2024-01-02", amount: "", unit: "days",
      }))).toBe(false);
    });

    it("rejects unparseable amount", () => {
      expect(isDateOpValid("add_duration", fields({
        primary: "2024-01-02", amount: "abc", unit: "days",
      }))).toBe(false);
    });

    it("accepts negative amounts", () => {
      expect(isDateOpValid("add_duration", fields({
        primary: "2024-01-02", amount: "-7", unit: "days",
      }))).toBe(true);
    });

    it("rejects months/years (not in v1)", () => {
      expect(isDateOpValid("add_duration", fields({
        primary: "2024-01-02", amount: "1", unit: "months",
      }))).toBe(false);
    });

    it.each(DURATION_UNITS)("accepts duration unit '%s'", (unit) => {
      expect(isDateOpValid("add_duration", fields({
        primary: "2024-01-02", amount: "1", unit,
      }))).toBe(true);
    });
  });

  describe("date_diff", () => {
    it("requires both dates and a duration unit", () => {
      expect(isDateOpValid("date_diff", fields({
        primary: "2024-01-05", secondary: "2024-01-02", unit: "days",
      }))).toBe(true);
      expect(isDateOpValid("date_diff", fields({
        primary: "2024-01-05", unit: "days",
      }))).toBe(false);
      expect(isDateOpValid("date_diff", fields({
        secondary: "2024-01-02", unit: "days",
      }))).toBe(false);
    });

    it("rejects unsupported units", () => {
      expect(isDateOpValid("date_diff", fields({
        primary: "2024-01-05", secondary: "2024-01-02", unit: "months",
      }))).toBe(false);
    });
  });

  describe("to_epoch", () => {
    it("requires primary and a valid epoch unit", () => {
      expect(isDateOpValid("to_epoch", fields({ primary: "2024-01-02", unit: "seconds" }))).toBe(true);
      expect(isDateOpValid("to_epoch", fields({ primary: "2024-01-02", unit: "millis" }))).toBe(true);
    });

    it("rejects duration units (days/weeks not valid for epoch)", () => {
      expect(isDateOpValid("to_epoch", fields({
        primary: "2024-01-02", unit: "days",
      }))).toBe(false);
    });

    it.each(EPOCH_UNITS)("accepts epoch unit '%s'", (unit) => {
      expect(isDateOpValid("to_epoch", fields({ primary: "2024-01-02", unit }))).toBe(true);
    });
  });
});
