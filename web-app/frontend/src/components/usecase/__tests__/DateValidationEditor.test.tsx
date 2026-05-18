/**
 * Component tests for DateValidationEditor (Task 9).
 *
 * Covers:
 *   - Operator dropdown shows all five spec'd operators
 *   - Non-equals_within operators show a single value input that
 *     forwards typed input through validation_value as-is (preserves
 *     literals and {{ var }} references)
 *   - equals_within reveals tolerance + unit + date inputs and serializes
 *     them as the JSON shape expected by the backend
 *   - Switching operators carries values intelligently
 */

import { useState } from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import DateValidationEditor from "../DateValidationEditor";


/**
 * Stateful test harness — mirrors how StepFormModal actually owns the
 * validationOperator / validationValue state so the controlled Input
 * receives an up-to-date `value` after each keystroke. The vi.fn spies
 * record every call so assertions can inspect the call sequence; the
 * harness mirrors each call into local state to keep the editor
 * controlled.
 */
function setup(initial: { operator: string; value: string }) {
  const setOp = vi.fn();
  const setValue = vi.fn();

  function Harness() {
    const [op, setOpState] = useState(initial.operator);
    const [value, setValueState] = useState(initial.value);
    return (
      <DateValidationEditor
        validationOperator={op}
        setValidationOperator={(next) => {
          setOp(next);
          setOpState(next);
        }}
        validationValue={value}
        setValidationValue={(next) => {
          setValue(next);
          setValueState(next);
        }}
      />
    );
  }

  render(<Harness />);
  return { setOp, setValue };
}


describe("DateValidationEditor — operator dropdown", () => {
  it("shows the five operators in the menu", async () => {
    const user = userEvent.setup();
    setup({ operator: "equals", value: "" });

    await user.click(screen.getByRole("button", { name: /equals/i }));

    // Wait for the listbox; then check each operator label is present.
    expect(await screen.findByText("Before")).toBeInTheDocument();
    expect(screen.getByText("After")).toBeInTheDocument();
    // Multiple "Equals" matches (the trigger and the option) — getAllByText.
    expect(screen.getAllByText(/^equals$/i).length).toBeGreaterThan(0);
    expect(screen.getByText("Not Equals")).toBeInTheDocument();
    expect(screen.getByText(/Equals Within/i)).toBeInTheDocument();
  });

  it("calls setValidationOperator when a new operator is picked", async () => {
    const user = userEvent.setup();
    const { setOp } = setup({ operator: "equals", value: "" });

    await user.click(screen.getByRole("button", { name: /equals/i }));
    await user.click(await screen.findByText("Before"));

    expect(setOp).toHaveBeenCalledWith("before");
  });
});


describe("DateValidationEditor — non-equals_within operators", () => {
  it("shows a single 'Expected Date' input for 'before'", () => {
    setup({ operator: "before", value: "2024-01-02" });
    expect(screen.getByText(/Expected Date/i)).toBeInTheDocument();
    expect(screen.queryByText(/Tolerance/i)).not.toBeInTheDocument();
  });

  it("forwards typed text through setValidationValue verbatim", async () => {
    const user = userEvent.setup();
    const { setValue } = setup({ operator: "equals", value: "" });

    const input = screen.getByPlaceholderText(/2024-01-02 or/);
    await user.type(input, "2024-01-02");

    expect(setValue).toHaveBeenLastCalledWith("2024-01-02");
  });

  it("preserves {{ var }} references typed into the input", async () => {
    const user = userEvent.setup();
    const { setValue } = setup({ operator: "before", value: "" });

    const input = screen.getByPlaceholderText(/2024-01-02 or/);
    // userEvent.type treats { as a special-key start. To type a literal {{
    // (the double-brace variable syntax), each literal { needs to be doubled
    // in the input string. So {{{{ produces {{ in the editor.
    await user.type(input, "{{{{ baseline_date }}");

    // Last call carries the full string the user typed.
    const lastCall = setValue.mock.calls.at(-1)?.[0];
    expect(lastCall).toBe("{{ baseline_date }}");
  });
});


describe("DateValidationEditor — equals_within composite UI", () => {
  it("renders comparison date, tolerance, and unit inputs", () => {
    setup({ operator: "equals_within", value: "" });
    expect(screen.getByText(/Comparison Date/i)).toBeInTheDocument();
    expect(screen.getByText(/^Tolerance$/i)).toBeInTheDocument();
    expect(screen.getByText(/^Unit$/i)).toBeInTheDocument();
  });

  it("hydrates fields from existing JSON validation_value", () => {
    const value = JSON.stringify({
      date: "2024-01-02T15:00:00+00:00",
      tolerance: 5,
      unit: "minutes",
    });
    setup({ operator: "equals_within", value });

    expect(screen.getByDisplayValue("2024-01-02T15:00:00+00:00")).toBeInTheDocument();
    expect(screen.getByDisplayValue("5")).toBeInTheDocument();
    // Unit is shown in a Select; check the displayed selection text.
    expect(screen.getAllByText("minutes").length).toBeGreaterThan(0);
  });

  it("serializes typed date into the JSON payload", async () => {
    const user = userEvent.setup();
    const initialValue = JSON.stringify({ date: "", tolerance: 5, unit: "minutes" });
    const { setValue } = setup({ operator: "equals_within", value: initialValue });

    const dateInput = screen.getByPlaceholderText(/2024-01-02T15:00:00\+00:00/);
    await user.type(dateInput, "2024-01-02");

    const lastCall = setValue.mock.calls.at(-1)?.[0];
    const parsed = JSON.parse(lastCall);
    expect(parsed.date).toBe("2024-01-02");
    expect(parsed.tolerance).toBe(5);
    expect(parsed.unit).toBe("minutes");
  });

  it("serializes typed tolerance into the JSON payload", async () => {
    const user = userEvent.setup();
    const initialValue = JSON.stringify({
      date: "2024-01-02",
      tolerance: 0,
      unit: "minutes",
    });
    const { setValue } = setup({ operator: "equals_within", value: initialValue });

    const toleranceInput = screen.getByPlaceholderText("5");
    // Existing value renders as "0" — clear and retype.
    await user.clear(toleranceInput);
    await user.type(toleranceInput, "10");

    const lastCall = setValue.mock.calls.at(-1)?.[0];
    expect(JSON.parse(lastCall).tolerance).toBe(10);
  });

  it("serializes a unit selection into the JSON payload", async () => {
    const user = userEvent.setup();
    const initialValue = JSON.stringify({
      date: "2024-01-02",
      tolerance: 5,
      unit: "minutes",
    });
    const { setValue } = setup({ operator: "equals_within", value: initialValue });

    // The unit select trigger reads "minutes"; click and pick "hours".
    const unitTrigger = screen.getAllByRole("button").find((el) =>
      el.textContent?.toLowerCase().includes("minutes"),
    )!;
    await user.click(unitTrigger);
    await user.click(await screen.findByText("hours"));

    const lastCall = setValue.mock.calls.at(-1)?.[0];
    expect(JSON.parse(lastCall).unit).toBe("hours");
  });
});


describe("DateValidationEditor — operator transitions", () => {
  it("on switch from 'equals' to 'equals_within', carries the existing date into the JSON payload", async () => {
    const user = userEvent.setup();
    const { setOp, setValue } = setup({
      operator: "equals",
      value: "2024-01-02",
    });

    await user.click(screen.getByRole("button", { name: /equals/i }));
    await user.click(await screen.findByText(/Equals Within/i));

    expect(setOp).toHaveBeenCalledWith("equals_within");
    // setValue must have been called with a JSON payload carrying the date.
    const jsonCall = setValue.mock.calls
      .map(([v]) => v)
      .find((v) => typeof v === "string" && v.startsWith("{"));
    expect(jsonCall).toBeDefined();
    const parsed = JSON.parse(jsonCall);
    expect(parsed.date).toBe("2024-01-02");
  });

  it("on switch from 'equals_within' back to 'equals', extracts just the date", async () => {
    const user = userEvent.setup();
    const value = JSON.stringify({
      date: "2024-01-02T15:00:00+00:00",
      tolerance: 5,
      unit: "minutes",
    });
    const { setOp, setValue } = setup({ operator: "equals_within", value });

    // Click the operator trigger (label is "Equals Within (tolerance)").
    await user.click(screen.getByRole("button", { name: /equals within/i }));
    // Click the plain "Equals" option (not "Equals Within" or "Not Equals").
    const options = await screen.findAllByText(/^equals$/i);
    // The first "Equals" in the listbox is the option.
    await user.click(options[options.length - 1]);

    expect(setOp).toHaveBeenCalledWith("equals");
    expect(setValue).toHaveBeenCalledWith("2024-01-02T15:00:00+00:00");
  });
});
