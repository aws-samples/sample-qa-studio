/**
 * Pure helpers for the `repeat` step's inline dataset (columns + rows).
 *
 * Mirrors the server rules in web-app/lambdas/endpoints/repeat_validation.py
 * so the editor can disable Save and show the same messages the API would
 * return. The server stays authoritative.
 */

import type { ApplicationDatasetSummary } from '../../utils/api';

export const MAX_REPEAT_COLUMNS = 20;
export const MAX_REPEAT_ROWS = 100;
const MAX_REPEAT_DATASET_BYTES = 200 * 1024;

export const RESERVED_REPEAT_COLUMN_NAMES: ReadonlySet<string> = new Set([
  'UniqueID', 'Time', 'ExecutionID', 'CreatedAt', 'RepeatIndex', 'RepeatTotal',
]);

const IDENTIFIER_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

export interface RepeatDataset {
  columns: string[];
  rows: string[][];
}

export function emptyRepeatDataset(): RepeatDataset {
  return { columns: ['value'], rows: [['']] };
}

/** Validate a dataset; returns server-equivalent error messages (empty = valid). */
export function validateRepeatDataset(columns: string[], rows: string[][]): string[] {
  const errors: string[] = [];
  if (columns.length < 1) errors.push('repeat_columns must contain at least 1 column');
  if (columns.length > MAX_REPEAT_COLUMNS) {
    errors.push(`repeat_columns must contain at most ${MAX_REPEAT_COLUMNS} columns`);
  }
  for (const column of columns) {
    if (!IDENTIFIER_RE.test(column)) {
      errors.push(
        `repeat column "${column}" is not a valid identifier (letters, digits and underscores, not starting with a digit)`,
      );
    } else if (RESERVED_REPEAT_COLUMN_NAMES.has(column)) {
      errors.push(`repeat column "${column}" is a reserved name`);
    }
  }
  if (new Set(columns).size !== columns.length) errors.push('repeat_columns must be unique');

  if (rows.length < 1) errors.push('repeat_rows must contain at least 1 row');
  if (rows.length > MAX_REPEAT_ROWS) errors.push(`repeat_rows must contain at most ${MAX_REPEAT_ROWS} rows`);
  rows.forEach((row, index) => {
    if (row.length !== columns.length) {
      errors.push(
        `repeat_rows row ${index + 1} has ${row.length} cells but ${columns.length} cells are expected`,
      );
    }
  });

  if (errors.length === 0) {
    const size = JSON.stringify(columns).length + JSON.stringify(rows).length;
    if (size > MAX_REPEAT_DATASET_BYTES) {
      errors.push(
        `repeat dataset is too large (${size} bytes; the limit is ${MAX_REPEAT_DATASET_BYTES} bytes / 200 KB)`,
      );
    }
  }
  return errors;
}

export function isRepeatDatasetValid(columns: string[], rows: string[][]): boolean {
  return validateRepeatDataset(columns, rows).length === 0;
}

/**
 * Parse pasted CSV text: first non-blank line is the header, remaining
 * non-blank lines are rows. Handles double-quoted cells with escaped
 * quotes (""). Short rows are padded with "" so every row has the header
 * length; longer rows are truncated.
 */
export function parseCsvText(text: string): RepeatDataset {
  const lines = text
    .split(/\r?\n/)
    .filter((line) => line.trim() !== '');
  if (lines.length === 0) return { columns: [], rows: [] };
  const columns = parseCsvLine(lines[0]).map((c) => c.trim());
  const rows = lines.slice(1).map((line) => {
    const cells = parseCsvLine(line);
    const normalized = cells.slice(0, columns.length);
    while (normalized.length < columns.length) normalized.push('');
    return normalized;
  });
  return { columns, rows };
}

function parseCsvLine(line: string): string[] {
  const cells: string[] = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (line[i + 1] === '"') {
          current += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        current += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ',') {
      cells.push(current);
      current = '';
    } else {
      current += ch;
    }
  }
  cells.push(current);
  return cells;
}

/** Human summary for list views: `3 rows · email, role`. */
export function describeRepeatDataset(columns: string[] | undefined, rows: string[][] | undefined): string {
  const rowCount = rows?.length ?? 0;
  const rowLabel = `${rowCount} ${rowCount === 1 ? 'row' : 'rows'}`;
  const columnLabel = (columns ?? []).join(', ');
  return columnLabel ? `${rowLabel} · ${columnLabel}` : rowLabel;
}

/**
 * Human summary for a repeat that references an application dataset
 * (`dataset_id`): `Application dataset: customers · 5 rows · 3 columns`.
 * The step record carries only the id; the name and counts come from the
 * application's dataset list, which the page may not have (yet).
 */
export function describeApplicationDataset(dataset: ApplicationDatasetSummary | undefined): string {
  if (!dataset) return 'Application dataset (not loaded)';
  const rows = `${dataset.row_count} ${dataset.row_count === 1 ? 'row' : 'rows'}`;
  const columns = `${dataset.column_count} ${dataset.column_count === 1 ? 'column' : 'columns'}`;
  return `Application dataset: ${dataset.name} · ${rows} · ${columns}`;
}
