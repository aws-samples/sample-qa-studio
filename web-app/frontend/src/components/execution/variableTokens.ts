/**
 * Splits a step template (`instruction` / `validation_value`) into text and
 * variable segments and classifies each `{{name}}` the way the runner
 * substitutes it (`qa-studio-cli/qa_studio_cli/runner/template_parser.py`).
 * Pure: no React, no API calls.
 */

import { executionIdOf, type ExecutionVariablesResponse } from '../../utils/api';

export type VariableKind = 'predefined' | 'runtime' | 'regular' | 'undefined';

export type TemplateSegment =
  | { type: 'text'; text: string }
  | { type: 'variable'; name: string; kind: VariableKind; display: string; placeholder: boolean };

export interface VariableContext {
  executionId: string;
  createdAt?: string;
  executionVariables: Record<string, string>;
  runtimeVariables: Record<string, string>;
  pendingRuntimeNames: Set<string>;
}

/** The fields of an execution record the resolver reads (`GET usecase/{id}/executions/{executionId}`). */
export interface ExecutionRef {
  sk?: string;
  execution_id?: string;
  created_at?: string;
}

/** A step's dataset row (`row_variables`); `RepeatIndex` / `RepeatTotal` arrive as numbers. */
type RowVariables = Record<string, string | number>;

/** `{{` + inner text without braces + `}}`; the inner text is checked by `classify`. */
const TOKEN = /\{\{([^{}]*)\}\}/g;

/**
 * Built-ins the runner fills in itself. The badge never shows their value,
 * only this label (uppercase, italic placeholder). They beat every other
 * variable of the same name.
 */
const BUILT_IN_LABELS: Record<string, string> = {
  UniqueID: 'UNIQUE_ID',
  Time: 'TIMESTAMP',
  ExecutionID: 'EXECUTION_ID',
  CreatedAt: 'CREATED_AT',
};

/** Predefined only on steps unrolled from a repeat (they come with `row_variables`). */
const REPEAT_LABELS: Record<string, string> = {
  RepeatIndex: 'REPEAT_INDEX',
  RepeatTotal: 'REPEAT_TOTAL',
};

/** Shown for a resolved value that is the empty string; the runner substitutes `''`. */
const EMPTY_VALUE = 'EMPTY_VALUE';

/** Shown for a token the runner leaves unresolved. */
const UNDEFINED_VALUE = 'UNDEFINED_VALUE';

type VariableSegment = Extract<TemplateSegment, { type: 'variable' }>;

/** Own-property lookup, so `{{toString}}` never resolves to `Object.prototype`. */
function lookup(source: Record<string, string | number> | undefined, name: string): string | undefined {
  if (!source || !Object.prototype.hasOwnProperty.call(source, name)) return undefined;
  return String(source[name]);
}

/** A badge showing a label instead of a value (rendered in italics). */
function placeholderSegment(name: string, kind: VariableKind, label: string): VariableSegment {
  return { type: 'variable', name, kind, display: label, placeholder: true };
}

/** A badge showing a resolved value; an empty value is flagged as `EMPTY_VALUE`. */
function valueSegment(name: string, kind: VariableKind, value: string): VariableSegment {
  if (value === '') return placeholderSegment(name, kind, EMPTY_VALUE);
  return { type: 'variable', name, kind, display: value, placeholder: false };
}

/** First match wins; mirrors `TemplateParser._merged_variables` (user < row < runtime < built-ins). */
function classify(name: string, ctx: VariableContext, rowVariables: RowVariables | undefined): VariableSegment {
  const builtIn = lookup(BUILT_IN_LABELS, name);
  if (builtIn !== undefined) return placeholderSegment(name, 'predefined', builtIn);

  const runtime = lookup(ctx.runtimeVariables, name);
  if (runtime !== undefined) return valueSegment(name, 'runtime', runtime);

  const row = lookup(rowVariables, name);
  if (row !== undefined) {
    const repeatLabel = lookup(REPEAT_LABELS, name);
    return repeatLabel !== undefined
      ? placeholderSegment(name, 'predefined', repeatLabel)
      : valueSegment(name, 'regular', row);
  }

  const regular = lookup(ctx.executionVariables, name);
  if (regular !== undefined) return valueSegment(name, 'regular', regular);

  if (ctx.pendingRuntimeNames.has(name)) return placeholderSegment(name, 'runtime', name);
  return placeholderSegment(name, 'undefined', UNDEFINED_VALUE);
}

/**
 * Splits `text` into text and variable segments. The runner substitutes only
 * an exact `{{name}}`, so a token with whitespace inside the braces is
 * `undefined` (named by its trimmed inner text). A token whose inner text is
 * empty or only whitespace is not a variable and stays text.
 */
export function resolveTemplate(text: string, ctx: VariableContext, rowVariables?: RowVariables): TemplateSegment[] {
  const segments: TemplateSegment[] = [];
  let textStart = 0;
  for (const match of text.matchAll(TOKEN)) {
    const inner = match[1];
    const name = inner.trim();
    if (!name) continue;

    const start = match.index ?? 0;
    if (start > textStart) segments.push({ type: 'text', text: text.slice(textStart, start) });
    segments.push(name === inner ? classify(name, ctx, rowVariables) : placeholderSegment(name, 'undefined', UNDEFINED_VALUE));
    textStart = start + match[0].length;
  }
  if (textStart < text.length) segments.push({ type: 'text', text: text.slice(textStart) });
  return segments;
}

/** A step's `capture_variable`, when it names one. */
function captureVariableOf(step: unknown): string | undefined {
  if (typeof step !== 'object' || step === null) return undefined;
  const name = (step as { capture_variable?: unknown }).capture_variable;
  return typeof name === 'string' && name !== '' ? name : undefined;
}

/**
 * Builds the resolver context from the execution record, its
 * `GET …/variables` response and the execution's steps. Missing parts are
 * treated as empty. A step's `capture_variable` that has no runtime value yet
 * is pending.
 */
export function buildVariableContext(
  execution: ExecutionRef | null | undefined,
  variables: ExecutionVariablesResponse | null | undefined,
  steps: unknown[],
): VariableContext {
  const executionId = execution?.execution_id || (execution?.sk ? executionIdOf({ sk: execution.sk }) : '');

  const runtimeVariables: Record<string, string> = {};
  for (const { key, value } of variables?.runtime_variables ?? []) {
    runtimeVariables[key] = String(value);
  }

  const executionVariables: Record<string, string> = {};
  for (const [key, value] of Object.entries(variables?.execution_variables ?? {})) {
    executionVariables[key] = String(value);
  }

  const pendingRuntimeNames = new Set<string>();
  for (const step of steps) {
    const name = captureVariableOf(step);
    if (name !== undefined && !Object.prototype.hasOwnProperty.call(runtimeVariables, name)) {
      pendingRuntimeNames.add(name);
    }
  }

  return {
    executionId,
    createdAt: execution?.created_at,
    executionVariables,
    runtimeVariables,
    pendingRuntimeNames,
  };
}
