/**
 * Component tests for DateFormatSelect (Task 8).
 *
 * Covers:
 *   - Initial render with default value
 *   - Selecting a curated format calls onChange with its strptime
 *   - Selecting "Custom…" reveals the input
 *   - Typing in the custom input forwards each keystroke as a format string
 *   - disableAutoDetect hides the auto-detect option
 *   - Loading an existing custom format pre-fills the custom input
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import DateFormatSelect from "../DateFormatSelect";


describe("DateFormatSelect", () => {
  it("renders a select with the format label", () => {
    render(<DateFormatSelect value="" onChange={() => {}} />);
    expect(screen.getByText(/format/i)).toBeInTheDocument();
  });

  it("hides the custom input by default", () => {
    render(<DateFormatSelect value="" onChange={() => {}} />);
    expect(
      screen.queryByPlaceholderText("%Y-%m-%dT%H:%M"),
    ).not.toBeInTheDocument();
  });

  it("shows the custom input when value is unmatched and non-empty", () => {
    // Hydrating with a format that doesn't match any curated entry should
    // open the custom input pre-filled with that value.
    render(<DateFormatSelect value="%Y-%m" onChange={() => {}} />);
    expect(
      screen.getByPlaceholderText("%Y-%m-%dT%H:%M"),
    ).toHaveValue("%Y-%m");
  });

  it("calls onChange with empty string when 'Auto-detect' is selected", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<DateFormatSelect value="%Y-%m-%d" onChange={onChange} />);

    // Open the dropdown.
    const select = screen.getByRole("button", { name: /iso date/i });
    await user.click(select);
    // Click the auto-detect option.
    await user.click(await screen.findByText(/auto-detect/i));

    expect(onChange).toHaveBeenCalledWith("");
  });

  it("calls onChange with the strptime of a curated format when selected", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<DateFormatSelect value="" onChange={onChange} />);

    const select = screen.getByRole("button", { name: /auto-detect/i });
    await user.click(select);
    // Pick "EU — slash" (%d/%m/%Y)
    await user.click(await screen.findByText(/EU — slash/));

    expect(onChange).toHaveBeenCalledWith("%d/%m/%Y");
  });

  it("reveals the custom input after picking 'Custom…'", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<DateFormatSelect value="" onChange={onChange} />);

    const select = screen.getByRole("button", { name: /auto-detect/i });
    await user.click(select);
    await user.click(await screen.findByText(/custom…/i));

    expect(
      screen.getByPlaceholderText("%Y-%m-%dT%H:%M"),
    ).toBeInTheDocument();
  });

  it("forwards typed characters from the custom input", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<DateFormatSelect value="" onChange={onChange} />);

    // Switch to custom mode.
    await user.click(screen.getByRole("button", { name: /auto-detect/i }));
    await user.click(await screen.findByText(/custom…/i));

    // Type into the custom input.
    const customInput = screen.getByPlaceholderText("%Y-%m-%dT%H:%M");
    await user.type(customInput, "%Y-%m");

    // userEvent.type fires onChange per keystroke; the last call should be
    // the full string.
    expect(onChange).toHaveBeenLastCalledWith("%Y-%m");
  });

  it("does not show 'Auto-detect' when disableAutoDetect is true", async () => {
    const user = userEvent.setup();
    render(
      <DateFormatSelect
        value="%Y-%m-%d"
        onChange={() => {}}
        disableAutoDetect
      />,
    );

    // Open the dropdown.
    await user.click(screen.getByRole("button", { name: /iso date/i }));

    // The auto-detect option should not appear in the menu.
    expect(screen.queryByText(/auto-detect/i)).not.toBeInTheDocument();
  });

  it("uses a custom label when provided", () => {
    render(
      <DateFormatSelect
        value=""
        onChange={() => {}}
        label="Output Format"
      />,
    );
    expect(screen.getByText("Output Format")).toBeInTheDocument();
  });

  it("includes a link to the Python strftime reference in custom mode", async () => {
    const user = userEvent.setup();
    render(<DateFormatSelect value="" onChange={() => {}} />);

    await user.click(screen.getByRole("button", { name: /auto-detect/i }));
    await user.click(await screen.findByText(/custom…/i));

    const link = screen.getByRole("link", { name: /python strftime reference/i });
    expect(link).toHaveAttribute(
      "href",
      "https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes",
    );
    expect(link).toHaveAttribute("target", "_blank");
  });
});
