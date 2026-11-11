import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

import {
  KeyValueManager,
  validateDrafts,
  type KeyValueApi,
  type KeyValueItem,
  type KeyValueLabels,
  type KeyValueManagerProps,
} from '../KeyValueManager';

const LABELS: KeyValueLabels = {
  singular: 'secret',
  plural: 'secrets',
  singularTitle: 'Secret',
  pluralTitle: 'Secrets',
  description: 'Manage secrets.',
  keyLabel: 'Secret Key',
  valueLabel: 'Secret Value',
  keyPlaceholder: 'e.g., api_key',
  valuePlaceholder: 'Enter the secret value',
  emptyText: 'No secrets configured for this usecase.',
};

const SECRET_VALUE = 'hunter2-very-secret';

function makeApi(initial: KeyValueItem[] = []): KeyValueApi & { list: ReturnType<typeof vi.fn> } {
  return {
    list: vi.fn().mockResolvedValue(initial),
    save: vi.fn().mockResolvedValue(undefined),
    remove: vi.fn().mockResolvedValue(undefined),
  };
}

function renderManager(api: KeyValueApi, masked = true, extra: Partial<KeyValueManagerProps> = {}) {
  return render(<KeyValueManager api={api} labels={LABELS} masked={masked} {...extra} />);
}

function addRow(index: number, key: string, value: string) {
  fireEvent.click(screen.getByRole('button', { name: 'Add new secret' }));
  fireEvent.change(screen.getByLabelText(`Secret Key ${index}`), { target: { value: key } });
  fireEvent.change(screen.getByLabelText(`Secret Value ${index}`), { target: { value } });
}

const saveButton = () => screen.getByRole('button', { name: 'Save Secrets' });

let consoleError: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
});
afterEach(() => {
  cleanup();
  consoleError.mockRestore();
});

describe('validateDrafts', () => {
  it('requires at least one row', () => {
    expect(validateDrafts([], LABELS)).toBe('Please add at least one secret');
  });

  it('requires a key and a value on every row', () => {
    expect(validateDrafts([{ key: 'a', value: ' ' }], LABELS)).toBe('All secrets must have both a key and value');
    expect(validateDrafts([{ key: '', value: 'v' }], LABELS)).toBe('All secrets must have both a key and value');
  });

  it('rejects duplicate keys after trimming', () => {
    expect(validateDrafts([{ key: 'a', value: '1' }, { key: ' a ', value: '2' }], LABELS)).toBe(
      'Duplicate secret keys found: a',
    );
  });

  it('accepts valid rows', () => {
    expect(validateDrafts([{ key: 'a', value: '1' }, { key: 'b', value: '2' }], LABELS)).toBeNull();
  });
});

describe('KeyValueManager — list', () => {
  it('shows the loading text, then the configured keys', async () => {
    const api = makeApi([{ key: 'api_key' }, { key: 'password' }]);
    renderManager(api);
    expect(screen.getByText('Loading secrets...')).toBeInTheDocument();
    expect(await screen.findByText('api_key')).toBeInTheDocument();
    expect(screen.getByText('password')).toBeInTheDocument();
    expect(screen.getByText('Current Secrets')).toBeInTheDocument();
    expect(screen.getByText('Add New Secrets')).toBeInTheDocument();
  });

  it('shows the empty text without entries', async () => {
    renderManager(makeApi([]));
    expect(await screen.findByText('No secrets configured for this usecase.')).toBeInTheDocument();
  });

  it('uses the caller-provided empty text', async () => {
    render(
      <KeyValueManager
        api={makeApi([])}
        labels={{ ...LABELS, emptyText: 'No secrets configured for this application.' }}
        masked
      />,
    );
    expect(await screen.findByText('No secrets configured for this application.')).toBeInTheDocument();
  });

  it('shows a load error', async () => {
    const api = makeApi();
    api.list.mockRejectedValue(new Error('boom'));
    renderManager(api);
    expect(await screen.findByText('Failed to load secrets')).toBeInTheDocument();
  });

  it('masked mode shows no value column and password inputs', async () => {
    renderManager(makeApi([{ key: 'api_key' }]), true);
    await screen.findByText('api_key');
    expect(screen.queryByRole('columnheader', { name: 'Secret Value' })).not.toBeInTheDocument();
    addRow(1, 'k', 'v');
    expect(screen.getByLabelText('Secret Value 1')).toHaveAttribute('type', 'password');
  });

  it('unmasked mode shows the values and text inputs', async () => {
    renderManager(makeApi([{ key: 'X-Env', value: 'staging' }]), false);
    expect(await screen.findByText('staging')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Secret Value' })).toBeInTheDocument();
    addRow(1, 'k', 'v');
    expect(screen.getByLabelText('Secret Value 1')).toHaveAttribute('type', 'text');
  });
});

describe('KeyValueManager — add, edit, save', () => {
  it('saves the rows with the current list, clears the form and reloads', async () => {
    const existing = [{ key: 'old' }];
    const api = makeApi(existing);
    renderManager(api);
    await screen.findByText('old');

    addRow(1, 'api_key', 'first');
    // edit the value of the row before saving
    fireEvent.change(screen.getByLabelText('Secret Value 1'), { target: { value: SECRET_VALUE } });
    addRow(2, 'token', 'abc');
    expect(saveButton()).not.toBeDisabled();

    api.list.mockResolvedValue([{ key: 'old' }, { key: 'api_key' }, { key: 'token' }]);
    fireEvent.click(saveButton());

    expect(await screen.findByText('Secrets saved successfully')).toBeInTheDocument();
    expect(api.save).toHaveBeenCalledWith(
      [{ key: 'api_key', value: SECRET_VALUE }, { key: 'token', value: 'abc' }],
      existing,
    );
    expect(await screen.findByText('token')).toBeInTheDocument();
    expect(screen.queryByLabelText('Secret Key 1')).not.toBeInTheDocument();
    expect(api.list).toHaveBeenCalledTimes(2);
  });

  it('never keeps a saved secret value in the DOM or the console', async () => {
    const api = makeApi([]);
    const { container } = renderManager(api);
    await screen.findByText('No secrets configured for this usecase.');

    addRow(1, 'password', SECRET_VALUE);
    api.list.mockResolvedValue([{ key: 'password' }]);
    fireEvent.click(saveButton());
    await screen.findByText('Secrets saved successfully');
    await screen.findByText('password');

    expect(container.innerHTML).not.toContain(SECRET_VALUE);
    expect(screen.queryByDisplayValue(SECRET_VALUE)).not.toBeInTheDocument();
    expect(JSON.stringify(consoleError.mock.calls)).not.toContain(SECRET_VALUE);
  });

  it('removes a draft row', async () => {
    renderManager(makeApi([]));
    await screen.findByText('No secrets configured for this usecase.');
    addRow(1, 'a', '1');
    addRow(2, 'b', '2');
    fireEvent.click(screen.getAllByRole('button', { name: 'Remove' })[0]);
    expect(screen.getByLabelText('Secret Key 1')).toHaveValue('b');
    expect(screen.queryByLabelText('Secret Key 2')).not.toBeInTheDocument();
  });

  it('rejects duplicate keys without calling the API', async () => {
    const api = makeApi([]);
    renderManager(api);
    await screen.findByText('No secrets configured for this usecase.');
    addRow(1, 'dup', '1');
    addRow(2, 'dup', '2');
    fireEvent.click(saveButton());
    expect(await screen.findByText('Duplicate secret keys found: dup')).toBeInTheDocument();
    expect(api.save).not.toHaveBeenCalled();
  });

  it('shows a save error, keeps the form and does not log the value', async () => {
    const api = makeApi([]);
    (api.save as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('denied'));
    renderManager(api);
    await screen.findByText('No secrets configured for this usecase.');
    addRow(1, 'password', SECRET_VALUE);
    fireEvent.click(saveButton());

    expect(await screen.findByText('Failed to save secrets')).toBeInTheDocument();
    expect(screen.getByLabelText('Secret Key 1')).toHaveValue('password');
    expect(JSON.stringify(consoleError.mock.calls)).not.toContain(SECRET_VALUE);
  });

  it('disables Save without rows', async () => {
    renderManager(makeApi([]));
    await screen.findByText('No secrets configured for this usecase.');
    expect(saveButton()).toBeDisabled();
  });
});

describe('KeyValueManager — inherited rows', () => {
  const INHERITED = { ownerSource: 'usecase', readOnlyRowLabel: 'Application' };
  const rows: KeyValueItem[] = [
    { key: 'own_key', source: 'usecase' },
    { key: 'admin_password', source: 'application' },
  ];

  it('renders rows from another source with a badge and without Delete', async () => {
    renderManager(makeApi(rows), true, INHERITED);
    await screen.findByText('own_key');
    const badges = screen.getAllByText('Application');
    expect(badges).toHaveLength(1);
    expect(badges[0].closest('tr')).toHaveTextContent('admin_password');
    const deleteButtons = screen.getAllByRole('button', { name: 'Delete' });
    expect(deleteButtons).toHaveLength(1);
    expect(deleteButtons[0].closest('tr')).toHaveTextContent('own_key');
  });

  it('renders no badge when readOnlyRowLabel is not given, even if rows carry a source', async () => {
    renderManager(makeApi(rows));
    await screen.findByText('own_key');
    expect(screen.queryByText('Application')).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Delete' })).toHaveLength(2);
  });

  it('hints that a draft with an inherited key overrides it', async () => {
    renderManager(makeApi(rows), true, INHERITED);
    await screen.findByText('own_key');
    addRow(1, 'other', 'v');
    expect(screen.queryByTestId('override-hint')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Secret Key 1'), { target: { value: ' admin_password ' } });
    expect(screen.getByTestId('override-hint')).toHaveTextContent(
      'Saving "admin_password" overrides the Application secret of the same name here.',
    );
    // A draft with an own key is a duplicate, not an override.
    fireEvent.change(screen.getByLabelText('Secret Key 1'), { target: { value: 'own_key' } });
    expect(screen.queryByTestId('override-hint')).not.toBeInTheDocument();
  });

  it('still saves an overriding draft through the adapter', async () => {
    const api = makeApi(rows);
    renderManager(api, true, INHERITED);
    await screen.findByText('own_key');
    addRow(1, 'admin_password', 'new');
    fireEvent.click(saveButton());
    await screen.findByText('Secrets saved successfully');
    expect(api.save).toHaveBeenCalledWith([{ key: 'admin_password', value: 'new' }], rows);
  });
});

describe('KeyValueManager — readOnly', () => {
  it('shows the list only: no Save, no Delete, no add form', async () => {
    renderManager(makeApi([{ key: 'api_key' }]), true, { readOnly: true });
    await screen.findByText('api_key');
    expect(screen.queryByRole('button', { name: 'Save Secrets' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add new secret' })).not.toBeInTheDocument();
    expect(screen.queryByText('Add New Secrets')).not.toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'Actions' })).not.toBeInTheDocument();
  });
});

describe('KeyValueManager — delete', () => {
  it('deletes a key with the current list and reloads', async () => {
    const existing = [{ key: 'api_key' }, { key: 'token' }];
    const api = makeApi(existing);
    renderManager(api);
    await screen.findByText('api_key');

    api.list.mockResolvedValue([{ key: 'token' }]);
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete' })[0]);

    expect(await screen.findByText('Secret "api_key" deleted successfully')).toBeInTheDocument();
    expect(api.remove).toHaveBeenCalledWith('api_key', existing);
    await waitFor(() => expect(screen.queryByText('api_key')).not.toBeInTheDocument());
  });

  it('shows a delete error', async () => {
    const api = makeApi([{ key: 'api_key' }]);
    (api.remove as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('nope'));
    renderManager(api);
    await screen.findByText('api_key');
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(await screen.findByText('Failed to delete secret "api_key"')).toBeInTheDocument();
  });
});
