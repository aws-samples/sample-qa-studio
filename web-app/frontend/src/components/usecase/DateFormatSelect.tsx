/**
 * Format selector for date transform operations.
 *
 * Renders a Cloudscape Select with a curated set of common date formats
 * (ISO, US regional, EU regional). Selecting "Custom…" reveals a free-text
 * strptime input. Selecting "Auto-detect" sends an empty format string
 * (the backend interprets empty == auto-detect ISO/epoch only).
 *
 * The component reports the effective strptime format string via
 * `onChange`. On mount, it hydrates its display state from the current
 * `value`: if the value matches a curated entry, that entry is selected;
 * if non-empty and unmatched, the "Custom…" mode is activated and the
 * input pre-fills with the value.
 */

import { useEffect, useMemo, useState } from "react";
import FormField from "@cloudscape-design/components/form-field";
import Input from "@cloudscape-design/components/input";
import Select, { SelectProps } from "@cloudscape-design/components/select";
import SpaceBetween from "@cloudscape-design/components/space-between";

interface FormatOption {
  /** Stable identifier shown in the dropdown. */
  label: string;
  /** Example human-readable date in this format. */
  example: string;
  /** Python strftime / strptime pattern. Empty = auto-detect. */
  strptime: string;
  /** Optional regional clarification shown as the dropdown description. */
  description?: string;
}

const AUTO_DETECT: FormatOption = {
  label: "Auto-detect (ISO 8601 / epoch)",
  example: "2024-01-02T15:04:05Z, 1704207845",
  strptime: "",
  description: "Use only when the value is already ISO 8601 or a Unix epoch.",
};

const CURATED_FORMATS: ReadonlyArray<FormatOption> = [
  { label: "ISO date", example: "2024-01-02", strptime: "%Y-%m-%d" },
  {
    label: "ISO date + time",
    example: "2024-01-02 15:04:05",
    strptime: "%Y-%m-%d %H:%M:%S",
  },
  {
    label: "US — slash",
    example: "01/02/2024",
    strptime: "%m/%d/%Y",
    description: "Month/day/year — US convention",
  },
  {
    label: "US — long month",
    example: "January 2, 2024",
    strptime: "%B %d, %Y",
  },
  {
    label: "US — short month",
    example: "Jan 2, 2024",
    strptime: "%b %d, %Y",
  },
  {
    label: "US — date + 12h time",
    example: "01/02/2024 3:04 PM",
    strptime: "%m/%d/%Y %I:%M %p",
  },
  {
    label: "EU — slash",
    example: "02/01/2024",
    strptime: "%d/%m/%Y",
    description: "Day/month/year — EU convention",
  },
  { label: "EU — dot", example: "02.01.2024", strptime: "%d.%m.%Y" },
  { label: "EU — dash", example: "02-01-2024", strptime: "%d-%m-%Y" },
  {
    label: "EU — date + 24h time",
    example: "02/01/2024 15:04",
    strptime: "%d/%m/%Y %H:%M",
  },
];

const CUSTOM_VALUE = "__custom__";

interface DateFormatSelectProps {
  /** Current strptime format string. Empty string = auto-detect. */
  value: string;
  /** Called when the effective format changes. */
  onChange: (format: string) => void;
  /**
   * When true, the "Auto-detect" entry is hidden. Use for `format_date`
   * which requires an explicit output format.
   */
  disableAutoDetect?: boolean;
  /** Field label, defaulting to "Format". */
  label?: string;
}

/**
 * Determine which dropdown option matches a given format string, or null
 * if the value is non-empty and doesn't match any curated entry (custom).
 */
function findMatchingOption(
  value: string,
  options: ReadonlyArray<FormatOption>,
): FormatOption | null {
  return options.find((opt) => opt.strptime === value) ?? null;
}

export default function DateFormatSelect({
  value,
  onChange,
  disableAutoDetect = false,
  label = "Format",
}: DateFormatSelectProps): JSX.Element {
  const allOptions = useMemo<ReadonlyArray<FormatOption>>(() => {
    return disableAutoDetect ? CURATED_FORMATS : [AUTO_DETECT, ...CURATED_FORMATS];
  }, [disableAutoDetect]);

  // Initial mode is "custom" if value is non-empty and no curated match.
  const [isCustomMode, setIsCustomMode] = useState<boolean>(
    () => value !== "" && findMatchingOption(value, allOptions) === null,
  );
  const [customValue, setCustomValue] = useState<string>(
    () => (findMatchingOption(value, allOptions) === null ? value : ""),
  );

  // If `value` changes externally (e.g. a step is loaded), re-derive mode.
  useEffect(() => {
    if (value === "" && !disableAutoDetect) {
      setIsCustomMode(false);
      setCustomValue("");
      return;
    }
    const match = findMatchingOption(value, allOptions);
    if (match) {
      setIsCustomMode(false);
    } else if (value !== "") {
      setIsCustomMode(true);
      setCustomValue(value);
    }
  }, [value, allOptions, disableAutoDetect]);

  const selectOptions: SelectProps.Option[] = [
    ...allOptions.map((opt) => ({
      label: opt.label,
      value: opt.strptime || "__auto__",
      description: opt.description
        ? `${opt.description}  ·  ${opt.example}  ·  ${opt.strptime || "(no format)"}`
        : `${opt.example}  ·  ${opt.strptime || "(no format)"}`,
    })),
    {
      label: "Custom…",
      value: CUSTOM_VALUE,
      description: "Free-form Python strptime pattern",
    },
  ];

  const selectedDropdownValue = isCustomMode
    ? CUSTOM_VALUE
    : findMatchingOption(value, allOptions)?.strptime || (allOptions[0]?.strptime ?? "");
  const selectedNormalized =
    selectedDropdownValue === "" ? "__auto__" : selectedDropdownValue;

  const handleSelectChange = (next: string) => {
    if (next === CUSTOM_VALUE) {
      setIsCustomMode(true);
      // Forward the current custom buffer (may be empty until user types).
      onChange(customValue);
      return;
    }
    setIsCustomMode(false);
    onChange(next === "__auto__" ? "" : next);
  };

  const handleCustomChange = (next: string) => {
    setCustomValue(next);
    onChange(next);
  };

  return (
    <SpaceBetween direction="vertical" size="xs">
      <FormField label={label} stretch>
        <Select
          selectedOption={
            selectOptions.find((opt) => opt.value === selectedNormalized) ?? null
          }
          onChange={({ detail }) =>
            handleSelectChange(detail.selectedOption?.value ?? "")
          }
          options={selectOptions}
        />
      </FormField>
      {isCustomMode && (
        <FormField
          label="Custom strptime pattern"
          stretch
          description={
            <>
              Python strptime syntax. See the{" "}
              <a
                href="https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes"
                target="_blank"
                rel="noopener noreferrer"
              >
                Python strftime reference
              </a>
              .
            </>
          }
        >
          <Input
            value={customValue}
            onChange={({ detail }) => handleCustomChange(detail.value)}
            placeholder="%Y-%m-%dT%H:%M"
          />
        </FormField>
      )}
    </SpaceBetween>
  );
}
