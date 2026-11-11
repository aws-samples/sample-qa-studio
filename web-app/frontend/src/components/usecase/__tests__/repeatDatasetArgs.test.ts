import { describe, it, expect } from 'vitest';

import {
  MAX_REPEAT_COLUMNS,
  MAX_REPEAT_ROWS,
  RESERVED_REPEAT_COLUMN_NAMES,
  describeApplicationDataset,
  describeRepeatDataset,
  isRepeatDatasetValid,
  parseCsvText,
  validateRepeatDataset,
} from '../repeatDatasetArgs';

describe('validateRepeatDataset', () => {
  it('accepts a well-formed dataset', () => {
    expect(validateRepeatDataset(['email', 'role'], [['a', 'admin'], ['b', 'viewer']])).toEqual([]);
  });

  it('requires at least one column and one row', () => {
    const errors = validateRepeatDataset([], []);
    expect(errors).toContain('repeat_columns must contain at least 1 column');
    expect(errors).toContain('repeat_rows must contain at least 1 row');
  });

  it('enforces the column and row caps', () => {
    const columns = Array.from({ length: MAX_REPEAT_COLUMNS + 1 }, (_, i) => `c${i}`);
    const rows = Array.from({ length: MAX_REPEAT_ROWS + 1 }, () => columns.map(() => 'x'));
    const errors = validateRepeatDataset(columns, rows);
    expect(errors).toContain(`repeat_columns must contain at most ${MAX_REPEAT_COLUMNS} columns`);
    expect(errors).toContain(`repeat_rows must contain at most ${MAX_REPEAT_ROWS} rows`);
  });

  it.each(['1abc', 'has space', 'dash-ed', ''])('rejects identifier %j', (bad) => {
    expect(validateRepeatDataset([bad], [['x']]).some((e) => e.includes('identifier'))).toBe(true);
  });

  it.each([...RESERVED_REPEAT_COLUMN_NAMES])('rejects reserved name %s', (name) => {
    expect(validateRepeatDataset([name], [['x']])).toContain(`repeat column "${name}" is a reserved name`);
  });

  it('rejects duplicate columns', () => {
    expect(validateRepeatDataset(['a', 'a'], [['1', '2']])).toContain('repeat_columns must be unique');
  });

  it('rejects ragged rows with the server message', () => {
    expect(validateRepeatDataset(['a', 'b'], [['1']])).toContain(
      'repeat_rows row 1 has 1 cells but 2 cells are expected',
    );
  });

  it('rejects datasets over 200 KB', () => {
    const errors = validateRepeatDataset(['a'], [['x'.repeat(200 * 1024)]]);
    expect(errors.some((e) => e.includes('200 KB'))).toBe(true);
  });

  it('isRepeatDatasetValid mirrors the error list', () => {
    expect(isRepeatDatasetValid(['a'], [['1']])).toBe(true);
    expect(isRepeatDatasetValid(['UniqueID'], [['1']])).toBe(false);
  });
});

describe('parseCsvText', () => {
  it('uses the first line as columns and the rest as rows', () => {
    expect(parseCsvText('email,role\na@x.test,admin\nb@x.test,viewer\n')).toEqual({
      columns: ['email', 'role'],
      rows: [['a@x.test', 'admin'], ['b@x.test', 'viewer']],
    });
  });

  it('skips blank lines and pads short rows', () => {
    expect(parseCsvText('a,b\n\n1\n')).toEqual({ columns: ['a', 'b'], rows: [['1', '']] });
  });

  it('handles quoted cells with commas and escaped quotes', () => {
    expect(parseCsvText('name\n"Doe, Jane"\n"say ""hi"""')).toEqual({
      columns: ['name'],
      rows: [['Doe, Jane'], ['say "hi"']],
    });
  });

  it('returns an empty dataset for empty text', () => {
    expect(parseCsvText('   \n')).toEqual({ columns: [], rows: [] });
  });
});

describe('describeRepeatDataset', () => {
  it('summarises rows and columns', () => {
    expect(describeRepeatDataset(['email', 'role'], [['a', 'b'], ['c', 'd'], ['e', 'f']])).toBe('3 rows · email, role');
    expect(describeRepeatDataset(['x'], [['1']])).toBe('1 row · x');
    expect(describeRepeatDataset(undefined, undefined)).toBe('0 rows');
  });
});

describe('describeApplicationDataset', () => {
  const summary = {
    dataset_id: 'ds-1', name: 'customers', description: '', column_count: 3, row_count: 5, updated_at: '2026-01-01T00:00:00Z',
  };

  it('names the dataset with its counts', () => {
    expect(describeApplicationDataset(summary)).toBe('Application dataset: customers · 5 rows · 3 columns');
    expect(describeApplicationDataset({ ...summary, row_count: 1, column_count: 1 })).toBe(
      'Application dataset: customers · 1 row · 1 column',
    );
  });

  it('falls back when the dataset list is not available', () => {
    expect(describeApplicationDataset(undefined)).toBe('Application dataset (not loaded)');
  });
});
