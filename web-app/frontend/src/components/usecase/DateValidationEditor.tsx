/**
 * Editor for validation_type=date branches of validation/assertion steps.
 *
 * Renders the operator picker plus an operator-aware expected-value UI:
 *   - For most operators, a single Input for the comparison date.
 *   - For equals_within, three inputs (date, tolerance amount, unit)
 *     that are serialized into the JSON shape expected in
 *     validation_value (see dateValidationArgs.ts).
 *
 * Used from both the validation and assertion sections of StepFormModal,
 * so the date validation UI lives in one place.
 */

import FormField from "@cloudscape-design/components/form-field";
import Input from "@cloudscape-design/components/input";
import Select from "@cloudscape-design/components/select";
import SpaceBetween from "@cloudscape-design/components/space-between";

import {
  VALIDATION_DATE_OPERATOR_OPTIONS,
  VALIDATION_DATE_DURATION_UNITS,
  buildEqualsWithinValue,
  loadEqualsWithinFields,
} from "./dateValidationArgs";


interface DateValidationEditorProps {
  validationOperator: string;
  setValidationOperator: (op: string) => void;
  validationValue: string;
  setValidationValue: (value: string) => void;
}

export default function DateValidationEditor({
  validationOperator,
  setValidationOperator,
  validationValue,
  setValidationValue,
}: DateValidationEditorProps): JSX.Element {
  const isEqualsWithin = validationOperator === "equals_within";

  // For equals_within, we derive the three fields from the canonical
  // validation_value JSON every render. Each input change rebuilds the
  // JSON and writes it back via setValidationValue. No separate state to
  // keep in sync with validation_value.
  const equalsWithinFields = loadEqualsWithinFields(validationValue);
  const updateEqualsWithin = (
    field: "date" | "tolerance" | "unit",
    next: string,
  ) => {
    setValidationValue(
      buildEqualsWithinValue({ ...equalsWithinFields, [field]: next }),
    );
  };

  return (
    <SpaceBetween direction="vertical" size="m">
      <FormField label="Date Operator" stretch>
        <Select
          selectedOption={
            VALIDATION_DATE_OPERATOR_OPTIONS.find(
              (opt) => opt.value === validationOperator,
            ) ?? null
          }
          onChange={({ detail }) => {
            const next = detail.selectedOption?.value ?? "equals";
            // When switching INTO equals_within, ensure validationValue
            // becomes a JSON payload (carry over the old value as the
            // date if it was plain). When switching OUT, drop back to
            // just the date if the JSON has one, else clear.
            if (next === "equals_within" && validationOperator !== "equals_within") {
              const carriedDate = validationValue.trim();
              setValidationValue(
                buildEqualsWithinValue({
                  date: carriedDate,
                  tolerance: "",
                  unit: "minutes",
                }),
              );
            } else if (next !== "equals_within" && validationOperator === "equals_within") {
              setValidationValue(equalsWithinFields.date);
            }
            setValidationOperator(next);
          }}
          options={[...VALIDATION_DATE_OPERATOR_OPTIONS]}
        />
      </FormField>

      {!isEqualsWithin && (
        <FormField
          stretch
          label="Expected Date"
          description="ISO 8601 string, regional format with parse_date upstream, or {{ variable }} reference."
        >
          <Input
            value={validationValue}
            onChange={({ detail }) => setValidationValue(detail.value)}
            placeholder="2024-01-02 or {{ order_date }}"
          />
        </FormField>
      )}

      {isEqualsWithin && (
        <SpaceBetween direction="vertical" size="s">
          <FormField
            stretch
            label="Comparison Date"
            description="The date to compare against, with tolerance below."
          >
            <Input
              value={equalsWithinFields.date}
              onChange={({ detail }) => updateEqualsWithin("date", detail.value)}
              placeholder="2024-01-02T15:00:00+00:00 or {{ baseline_date }}"
            />
          </FormField>
          <FormField stretch label="Tolerance" description="Non-negative integer.">
            <Input
              value={equalsWithinFields.tolerance}
              onChange={({ detail }) => updateEqualsWithin("tolerance", detail.value)}
              placeholder="5"
              type="number"
            />
          </FormField>
          <FormField stretch label="Unit">
            <Select
              selectedOption={
                equalsWithinFields.unit
                  ? { label: equalsWithinFields.unit, value: equalsWithinFields.unit }
                  : null
              }
              onChange={({ detail }) =>
                updateEqualsWithin("unit", detail.selectedOption?.value ?? "")
              }
              options={VALIDATION_DATE_DURATION_UNITS.map((u) => ({
                label: u,
                value: u,
              }))}
              placeholder="Select a unit"
            />
          </FormField>
        </SpaceBetween>
      )}
    </SpaceBetween>
  );
}
