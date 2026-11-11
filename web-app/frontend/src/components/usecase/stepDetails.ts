/**
 * The per-step-type detail lines shown under a step's instruction in the step
 * cards (WorkflowStepsCard). The cards add their own lines around them
 * (instruction, assertion variable, empty repeat, cached trajectory age).
 */
import { describeApplicationDataset, describeRepeatDataset } from './repeatDatasetArgs';
import { numberOperatorText, stringOperatorText } from './operatorText';
import type { ApplicationDatasetSummary } from '../../utils/api';

/** Snake_case step fields the detail lines read (API field names). */
export interface StepDetailFields {
  step_type?: string;
  secret_key?: string;
  validation_type?: string;
  validation_operator?: string;
  validation_value?: string;
  capture_variable?: string;
  browser_action?: string;
  browser_args?: string;
  transform_operation?: string;
  network_url_pattern?: string | null;
  network_method?: string | null;
  network_request_body?: string | null;
  network_body_match_type?: string | null;
  network_mock_response?: string | null;
  network_mock_passthrough?: boolean | null;
  network_response_body?: string | null;
  network_response_body_match_type?: string | null;
  network_response_status?: number | null;
  repeat_columns?: string[];
  repeat_rows?: string[][];
  /** Repeat steps: the application dataset used instead of inline rows. */
  dataset_id?: string | null;
}

const EXPECTATION_TYPES = new Set(['bool', 'string', 'number']);

/** True when a validation/assertion step has a type its expectation line can describe. */
export function hasExpectation(step: StepDetailFields): boolean {
  return EXPECTATION_TYPES.has(step.validation_type ?? '');
}

/** "Validation: Text contains "x"", "Assertion: Number > 3", …; null for an unknown type. */
function expectationLine(prefix: 'Validation' | 'Assertion', step: StepDetailFields): string | null {
  switch (step.validation_type) {
    case 'bool':
      return `${prefix}: Boolean expects ${step.validation_value === 'true' ? 'True' : 'False'}`;
    case 'string':
      return `${prefix}: Text ${stringOperatorText(step.validation_operator)} "${step.validation_value}"`;
    case 'number':
      return `${prefix}: Number ${numberOperatorText(step.validation_operator)} ${step.validation_value}`;
    default:
      return null;
  }
}

function browserLines(step: StepDetailFields): string[] {
  const lines = [`Action: ${step.browser_action}`];
  if (step.browser_args) {
    try {
      const args = JSON.parse(step.browser_args);
      if (args.hard) lines.push('Hard reload');
      if (args.url) lines.push(`URL: ${args.url}`);
    } catch {
      // Malformed args: show the action only.
    }
  }
  return lines;
}

function networkLine(step: StepDetailFields): string {
  const parts = [`Network: ${step.network_method || 'any'} ${step.network_url_pattern}`];
  if (step.network_request_body) {
    parts.push(`req body (${step.network_body_match_type || 'exact'})`);
  }
  if (step.network_mock_response) {
    parts.push(step.network_mock_passthrough ? 'passthrough mock' : 'static mock');
  }
  if (step.network_response_status != null) {
    parts.push(`resp ${step.network_response_status}`);
  }
  if (step.network_response_body) {
    parts.push(`resp body (${step.network_response_body_match_type || 'subset'})`);
  }
  return parts.join(' · ');
}

/**
 * Detail lines for the step's type, in display order; empty when there is
 * nothing to add. `datasets` is the owning application's dataset list, used
 * to name the dataset of a `dataset_id` repeat.
 */
export function stepDetailLines(step: StepDetailFields, datasets: readonly ApplicationDatasetSummary[] = []): string[] {
  switch (step.step_type) {
    case 'repeat':
      if (step.dataset_id) {
        return [describeApplicationDataset(datasets.find((d) => d.dataset_id === step.dataset_id))];
      }
      return [describeRepeatDataset(step.repeat_columns, step.repeat_rows)];
    case 'secret':
      return step.secret_key ? [`Secret: ${step.secret_key}`] : [];
    case 'validation':
    case 'assertion': {
      const line = expectationLine(step.step_type === 'validation' ? 'Validation' : 'Assertion', step);
      return line ? [line] : [];
    }
    case 'retrieve_value':
      return step.capture_variable ? [`Captures variable: ${step.capture_variable}`] : [];
    case 'browser':
      return step.browser_action ? browserLines(step) : [];
    case 'transform':
      if (!step.transform_operation) return [];
      return [
        `Operation: ${step.transform_operation}`,
        ...(step.capture_variable ? [`→ {{ ${step.capture_variable} }}`] : []),
      ];
    case 'network_assertion':
      return step.network_url_pattern ? [networkLine(step)] : [];
    default:
      return [];
  }
}
