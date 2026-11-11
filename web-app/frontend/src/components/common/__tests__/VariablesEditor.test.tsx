/**
 * VariablesEditor: application-sourced rows are shown read-only with an
 * "Application" badge and never posted; use-case rows are edited in the
 * AttributeEditor and saved through the adapter; readOnly renders a table only.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

import { VariablesEditor, validateVariableRows, type VariableRow, type VariablesApi } from '../VariablesEditor';

const INHERITED: VariableRow[] = [
  { key: 'base_api', value: 'https://api.staging.example.com', source: 'application' },
  { key: 'region', value: 'eu-west-1', source: 'application' },
];
const OWN: VariableRow[] = [{ key: 'user', value: 'alice', source: 'usecase' }];

function makeApi(initial: VariableRow[] = []): VariablesApi & { list: ReturnType<typeof vi.fn>; save: ReturnType<typeof vi.fn> } {
  return {
    list: vi.fn().mockResolvedValue(initial),
    save: vi.fn().mockResolvedValue(undefined),
  };
}

const keyInput = (index: number) => screen.getByLabelText(`Key ${index}`);
const valueInput = (index: number) => screen.getByLabelText(`Value ${index}`);
const saveButton = () => screen.getByRole('button', { name: /Save/ });

function addRow(index: number, key: string, value: string) {
  fireEvent.click(screen.getByRole('button', { name: 'Add new variable' }));
  fireEvent.change(keyInput(index), { target: { value: key } });
  fireEvent.change(valueInput(index), { target: { value } });
}

let consoleError: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
});
afterEach(() => {
  cleanup();
  consoleError.mockRestore();
});

describe('validateVariableRows', () => {
  it('accepts an empty list and valid keys', () => {
    expect(validateVariableRows([])).toBeNull();
    expect(validateVariableRows([{ key: 'a_1', value: '' }, { key: '_B', value: 'x' }])).toBeNull();
  });

  it('rejects empty keys', () => {
    expect(validateVariableRows([{ key: '  ', value: 'x' }])).toBe('Every variable needs a key');
  });

  it('rejects keys outside the allowed pattern', () => {
    expect(validateVariableRows([{ key: '1abc', value: 'x' }])).toBe(
      'Invalid variable key "1abc": use letters, digits and underscores, not starting with a digit',
    );
    expect(validateVariableRows([{ key: 'a-b', value: 'x' }])).toContain('Invalid variable key "a-b"');
  });

  it('rejects duplicate keys after trimming', () => {
    expect(validateVariableRows([{ key: 'a', value: '1' }, { key: ' a ', value: '2' }])).toBe(
      'Duplicate variable keys found: a',
    );
  });

  it('rejects more than 100 rows', () => {
    const rows = Array.from({ length: 101 }, (_, i) => ({ key: `k${i}`, value: '' }));
    expect(validateVariableRows(rows)).toBe('At most 100 variables are allowed');
  });
});

describe('VariablesEditor — load', () => {
  it('shows a loading state, then inherited rows in a badged table and own rows in the editor', async () => {
    render(<VariablesEditor api={makeApi([...INHERITED, ...OWN])} />);
    expect(screen.getByText('Loading variables...')).toBeInTheDocument();

    expect(await screen.findByText('base_api')).toBeInTheDocument();
    expect(screen.getByText('https://api.staging.example.com')).toBeInTheDocument();
    expect(screen.getByText('Inherited from application')).toBeInTheDocument();
    expect(screen.getAllByText('Application')).toHaveLength(2);

    // own row is editable, inherited rows are not inputs
    expect(keyInput(1)).toHaveValue('user');
    expect(valueInput(1)).toHaveValue('alice');
    expect(screen.queryByLabelText('Key 2')).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('base_api')).not.toBeInTheDocument();
  });

  it('hides the inherited table when there are no application rows', async () => {
    render(<VariablesEditor api={makeApi(OWN)} />);
    await screen.findByDisplayValue('user');
    expect(screen.queryByText('Inherited from application')).not.toBeInTheDocument();
    expect(screen.queryByText('Application')).not.toBeInTheDocument();
  });

  it('treats rows without source as editable', async () => {
    render(<VariablesEditor api={makeApi([{ key: 'plain', value: '1' }])} />);
    expect(await screen.findByDisplayValue('plain')).toBeInTheDocument();
    expect(screen.queryByText('Application')).not.toBeInTheDocument();
  });

  it('shows the empty text without rows', async () => {
    render(<VariablesEditor api={makeApi([])} />);
    expect(await screen.findByText("No variables configured. Click 'Add new variable' to get started.")).toBeInTheDocument();
  });

  it('shows a load error', async () => {
    const api = makeApi();
    api.list.mockRejectedValue(new Error('boom'));
    render(<VariablesEditor api={api} />);
    expect(await screen.findByText('Failed to load variables')).toBeInTheDocument();
  });
});

describe('VariablesEditor — edit and save', () => {
  it('saves only the use-case rows, never the inherited ones', async () => {
    const api = makeApi([...INHERITED, ...OWN]);
    render(<VariablesEditor api={api} />);
    await screen.findByDisplayValue('user');
    expect(saveButton()).toBeDisabled();

    fireEvent.change(valueInput(1), { target: { value: 'bob' } });
    addRow(2, 'env', 'staging');
    expect(saveButton()).not.toBeDisabled();
    fireEvent.click(saveButton());

    await waitFor(() => expect(api.save).toHaveBeenCalledTimes(1));
    expect(api.save).toHaveBeenCalledWith([
      { key: 'user', value: 'bob', source: 'usecase' },
      { key: 'env', value: 'staging' },
    ]);
    expect(JSON.stringify(api.save.mock.calls)).not.toContain('base_api');
    expect(await screen.findByText('Variables saved')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Saved' })).toBeDisabled();
    // inherited rows are still shown after the save
    expect(screen.getByText('base_api')).toBeInTheDocument();
  });

  it('shows the override hint for a use-case row whose key matches an inherited key', async () => {
    render(<VariablesEditor api={makeApi([...INHERITED, ...OWN])} />);
    await screen.findByDisplayValue('user');
    expect(screen.queryByText('Overrides application value')).not.toBeInTheDocument();

    addRow(2, 'base_api', 'https://api.pr-42.example.com');
    expect(screen.getByText('Overrides application value')).toBeInTheDocument();

    fireEvent.change(keyInput(2), { target: { value: 'other' } });
    expect(screen.queryByText('Overrides application value')).not.toBeInTheDocument();
  });

  it('allows an override key and posts it with the own rows', async () => {
    const api = makeApi([...INHERITED]);
    render(<VariablesEditor api={api} />);
    await screen.findByText('base_api');
    addRow(1, 'base_api', 'override');
    fireEvent.click(saveButton());
    await waitFor(() => expect(api.save).toHaveBeenCalledWith([{ key: 'base_api', value: 'override' }]));
  });

  it('removes a row and resets changes', async () => {
    render(<VariablesEditor api={makeApi(OWN)} />);
    await screen.findByDisplayValue('user');
    addRow(2, 'b', '2');
    fireEvent.click(screen.getAllByRole('button', { name: 'Remove' })[0]);
    expect(keyInput(1)).toHaveValue('b');
    expect(screen.queryByLabelText('Key 2')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Reset Changes' }));
    expect(keyInput(1)).toHaveValue('user');
    expect(screen.queryByRole('button', { name: 'Reset Changes' })).not.toBeInTheDocument();
  });

  it('rejects invalid rows without calling the adapter', async () => {
    const api = makeApi([]);
    render(<VariablesEditor api={api} />);
    await screen.findByText("No variables configured. Click 'Add new variable' to get started.");
    addRow(1, 'dup', '1');
    addRow(2, 'dup', '2');
    fireEvent.click(saveButton());
    expect(await screen.findByText('Duplicate variable keys found: dup')).toBeInTheDocument();
    expect(api.save).not.toHaveBeenCalled();
  });

  it('trims keys before saving', async () => {
    const api = makeApi([]);
    render(<VariablesEditor api={api} />);
    await screen.findByText("No variables configured. Click 'Add new variable' to get started.");
    addRow(1, '  spaced ', 'v');
    fireEvent.click(saveButton());
    await waitFor(() => expect(api.save).toHaveBeenCalledWith([{ key: 'spaced', value: 'v' }]));
  });

  it('shows the server message on a save error and keeps the form', async () => {
    const api = makeApi(OWN);
    api.save.mockRejectedValue(new Error('Variable key limit exceeded'));
    render(<VariablesEditor api={api} />);
    await screen.findByDisplayValue('user');
    fireEvent.change(valueInput(1), { target: { value: 'bob' } });
    fireEvent.click(saveButton());
    expect(await screen.findByText('Failed to save variables: Variable key limit exceeded')).toBeInTheDocument();
    expect(valueInput(1)).toHaveValue('bob');
  });

  it('reloads from the adapter on refresh', async () => {
    const api = makeApi(OWN);
    render(<VariablesEditor api={api} />);
    await screen.findByDisplayValue('user');
    api.list.mockResolvedValue([{ key: 'user', value: 'carol', source: 'usecase' }]);
    fireEvent.click(screen.getByRole('button', { name: 'Refresh variables' }));
    expect(await screen.findByDisplayValue('carol')).toBeInTheDocument();
    expect(api.list).toHaveBeenCalledTimes(2);
  });

  it('lists the predefined variables', async () => {
    render(<VariablesEditor api={makeApi([])} />);
    await screen.findByText('Predefined Variables');
    fireEvent.click(screen.getByText('Predefined Variables'));
    expect(screen.getByText('{{UniqueID}}')).toBeInTheDocument();
    expect(screen.getByText('{{ExecutionID}}')).toBeInTheDocument();
  });
});

describe('VariablesEditor — readOnly', () => {
  it('renders every row in one table with the badge, and no Save, Add or Refresh', async () => {
    render(<VariablesEditor api={makeApi([...INHERITED, ...OWN])} readOnly />);
    expect(await screen.findByText('user')).toBeInTheDocument();
    expect(screen.getByText('alice')).toBeInTheDocument();
    expect(screen.getByText('base_api')).toBeInTheDocument();
    expect(screen.getAllByText('Application')).toHaveLength(2);
    expect(screen.getByText('Use case')).toBeInTheDocument();

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('shows no source column when no row is inherited', async () => {
    render(<VariablesEditor api={makeApi([{ key: 'plain', value: '1' }])} readOnly />);
    expect(await screen.findByText('plain')).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'Source' })).not.toBeInTheDocument();
  });

  it('shows the empty text without rows', async () => {
    render(<VariablesEditor api={makeApi([])} readOnly />);
    expect(await screen.findByText('No variables configured.')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
