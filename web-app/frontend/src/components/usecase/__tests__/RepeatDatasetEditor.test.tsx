/**
 * Component tests for RepeatDatasetEditor.
 *
 * The editor is controlled; the harness mirrors every onChange into local
 * state (same as StepFormModal) and records the payloads for assertions.
 */

import { useState } from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import RepeatDatasetEditor from '../RepeatDatasetEditor';
import type { RepeatDataset } from '../repeatDatasetArgs';

afterEach(() => cleanup());

function setup(initial: RepeatDataset) {
  const onChange = vi.fn();

  function Harness() {
    const [dataset, setDataset] = useState(initial);
    return (
      <RepeatDatasetEditor
        columns={dataset.columns}
        rows={dataset.rows}
        onChange={(next) => {
          onChange(next);
          setDataset(next);
        }}
      />
    );
  }

  render(<Harness />);
  return { onChange, last: () => onChange.mock.calls[onChange.mock.calls.length - 1][0] as RepeatDataset };
}

describe('RepeatDatasetEditor — grid', () => {
  it('renders one labelled input per cell and per column', () => {
    setup({ columns: ['email', 'role'], rows: [['a', 'admin'], ['b', 'viewer']] });
    expect(screen.getByLabelText('Column 1 name')).toHaveValue('email');
    expect(screen.getByLabelText('Column 2 name')).toHaveValue('role');
    expect(screen.getByLabelText('Row 1, email')).toHaveValue('a');
    expect(screen.getByLabelText('Row 2, role')).toHaveValue('viewer');
  });

  it('editing a cell emits the updated rows', async () => {
    const user = userEvent.setup();
    const { last } = setup({ columns: ['email'], rows: [['a']] });
    await user.type(screen.getByLabelText('Row 1, email'), 'x');
    expect(last()).toEqual({ columns: ['email'], rows: [['ax']] });
  });

  it('add row appends an empty row; add column appends a named column to every row', async () => {
    const user = userEvent.setup();
    const { last } = setup({ columns: ['email'], rows: [['a']] });
    await user.click(screen.getByRole('button', { name: 'Add row' }));
    expect(last()).toEqual({ columns: ['email'], rows: [['a'], ['']] });
    await user.click(screen.getByRole('button', { name: 'Add column' }));
    expect(last()).toEqual({ columns: ['email', 'column2'], rows: [['a', ''], ['', '']] });
  });

  it('remove row and remove column shrink the dataset', async () => {
    const user = userEvent.setup();
    const { last } = setup({ columns: ['email', 'role'], rows: [['a', 'admin'], ['b', 'viewer']] });
    await user.click(screen.getByRole('button', { name: 'Remove row 2' }));
    expect(last()).toEqual({ columns: ['email', 'role'], rows: [['a', 'admin']] });
    await user.click(screen.getByRole('button', { name: 'Remove column role' }));
    expect(last()).toEqual({ columns: ['email'], rows: [['a']] });
  });

  it('cannot remove the last column or the last row', () => {
    setup({ columns: ['email'], rows: [['a']] });
    expect(screen.getByRole('button', { name: 'Remove column email' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Remove row 1' })).toBeDisabled();
  });
});

describe('RepeatDatasetEditor — validation', () => {
  it('shows server-equivalent errors for a reserved column name', () => {
    setup({ columns: ['UniqueID'], rows: [['a']] });
    expect(screen.getByText(/repeat column "UniqueID" is a reserved name/)).toBeInTheDocument();
  });

  it('shows an identifier error while renaming', async () => {
    const user = userEvent.setup();
    setup({ columns: ['email'], rows: [['a']] });
    await user.type(screen.getByLabelText('Column 1 name'), ' x');
    expect(screen.getByText(/is not a valid identifier/)).toBeInTheDocument();
  });

  it('shows no error for a valid dataset', () => {
    setup({ columns: ['email'], rows: [['a']] });
    expect(screen.queryByText(/repeat_/)).not.toBeInTheDocument();
  });
});

describe('RepeatDatasetEditor — paste CSV', () => {
  it('replaces the grid after confirmation', async () => {
    const user = userEvent.setup();
    const { last, onChange } = setup({ columns: ['old'], rows: [['x']] });
    await user.click(screen.getByText('Paste CSV'));
    await user.type(screen.getByLabelText('CSV text'), 'email,role\na,admin\nb,viewer');
    await user.click(screen.getByRole('button', { name: 'Replace dataset with CSV' }));
    const alert = screen.getByText('Replace the current dataset?').closest('[role="alert"]') ?? document.body;
    expect(within(alert as HTMLElement).getByText(/replaces 1 column and 1 row with 2 columns and 2 rows/)).toBeInTheDocument();
    // Nothing applied until confirmed.
    expect(onChange).not.toHaveBeenCalled();
    await user.click(screen.getByTestId('confirm-replace-csv'));
    expect(last()).toEqual({ columns: ['email', 'role'], rows: [['a', 'admin'], ['b', 'viewer']] });
  });

  it('replace button is disabled while the CSV is empty', async () => {
    const user = userEvent.setup();
    setup({ columns: ['old'], rows: [['x']] });
    await user.click(screen.getByText('Paste CSV'));
    expect(screen.getByRole('button', { name: 'Replace dataset with CSV' })).toBeDisabled();
  });
});
