/**
 * DatasetFormModal — create / edit an application dataset on FormModal +
 * RepeatDatasetEditor: client validation (name rule, dataset rules), the
 * POST / PUT bodies, and how server 400 / 409 answers are shown.
 *
 * Cloudscape's Modal renders into a portal; queries go through `screen`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import createWrapper from '@cloudscape-design/components/test-utils/dom';

const { datasetsApi } = vi.hoisted(() => ({
  datasetsApi: {
    create: vi.fn(),
    update: vi.fn(),
  },
}));
vi.mock('../../../utils/api', () => ({ datasetsApi }));

import DatasetFormModal from '../DatasetFormModal';
import type { ApplicationDataset } from '../../../utils/api';

const EXISTING: ApplicationDataset = {
  dataset_id: 'ds-1',
  name: 'customers',
  description: 'Shop customers',
  columns: ['email', 'role'],
  rows: [['a@x.test', 'admin'], ['b@x.test', 'viewer']],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
  created_by: 'alice',
};

function renderModal(dataset: ApplicationDataset | null = null) {
  const onDismiss = vi.fn();
  const onSaved = vi.fn();
  render(<DatasetFormModal visible applicationId="app-1" dataset={dataset} onDismiss={onDismiss} onSaved={onSaved} />);
  return { onDismiss, onSaved };
}

/** Cloudscape Input renders the testid on a wrapper; the <input> is inside. */
function typeInto(testId: string, value: string) {
  const el = screen.getByTestId(testId);
  const input = el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' ? el : (el.querySelector('input, textarea') as HTMLElement);
  fireEvent.change(input, { target: { value } });
}

/** Error text of the Name form field (null when it shows none). */
const nameFieldError = () =>
  createWrapper(document.body).findFormField('[data-testid="dataset-form-name-field"]')!.findError()?.getElement().textContent ?? null;

const httpError = (status: number, body: Record<string, unknown>) => ({
  type: 'validation', message: String(body.error), retryable: false, status, body,
});

beforeEach(() => {
  datasetsApi.create.mockReset();
  datasetsApi.update.mockReset();
});
afterEach(() => {
  cleanup();
});

describe('DatasetFormModal — create', () => {
  it('renders the create header, the fields and the dataset grid with one empty column', () => {
    renderModal();
    expect(screen.getByText('Create dataset')).toBeInTheDocument();
    expect(screen.getByText('Name')).toBeInTheDocument();
    expect(screen.getByText('Description')).toBeInTheDocument();
    expect(screen.getByTestId('repeat-dataset-grid')).toBeInTheDocument();
    expect(screen.getByLabelText('Column 1 name')).toHaveValue('value');
    expect(screen.getByTestId('dataset-form-submit')).toHaveTextContent('Create');
  });

  it('requires a name and shows the rule for an invalid one on the Name field', async () => {
    const { onSaved } = renderModal();
    fireEvent.click(screen.getByTestId('dataset-form-submit'));
    expect(await screen.findByText('name is required')).toBeInTheDocument();

    typeInto('dataset-form-name-input', '1 bad');
    fireEvent.click(screen.getByTestId('dataset-form-submit'));
    await screen.findByText(/dataset name "1 bad" is invalid/);
    // Shown as the Name field's error, not as a page-level alert.
    expect(nameFieldError()).toMatch(/dataset name "1 bad" is invalid/);
    expect(screen.queryByTestId('dataset-form-server-errors')).toBeNull();
    expect(datasetsApi.create).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it('refuses an invalid dataset with the server-equivalent message', async () => {
    const user = userEvent.setup();
    const { onSaved } = renderModal();
    typeInto('dataset-form-name-input', 'customers');
    await user.clear(screen.getByLabelText('Column 1 name'));
    await user.type(screen.getByLabelText('Column 1 name'), 'UniqueID');
    fireEvent.click(screen.getByTestId('dataset-form-submit'));
    await waitFor(() => expect(screen.getAllByText(/repeat column "UniqueID" is a reserved name/).length).toBeGreaterThan(0));
    expect(datasetsApi.create).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it('POSTs the trimmed name, description, columns and rows and reports the saved dataset', async () => {
    const user = userEvent.setup();
    const saved = { ...EXISTING, dataset_id: 'ds-new', name: 'leads', description: 'Inbound', columns: ['email'], rows: [['a@x.test']] };
    datasetsApi.create.mockResolvedValue({ dataset: saved });
    const { onSaved, onDismiss } = renderModal();

    typeInto('dataset-form-name-input', '  leads ');
    typeInto('dataset-form-description-input', ' Inbound ');
    await user.clear(screen.getByLabelText('Column 1 name'));
    await user.type(screen.getByLabelText('Column 1 name'), 'email');
    await user.type(screen.getByLabelText('Row 1, email'), 'a@x.test');
    fireEvent.click(screen.getByTestId('dataset-form-submit'));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved));
    expect(datasetsApi.create).toHaveBeenCalledWith('app-1', {
      name: 'leads', description: 'Inbound', columns: ['email'], rows: [['a@x.test']],
    });
    expect(datasetsApi.update).not.toHaveBeenCalled();
    expect(onDismiss).toHaveBeenCalled();
  });

  it('shows a name conflict (409) on the Name field and stays open', async () => {
    const user = userEvent.setup();
    datasetsApi.create.mockRejectedValue(httpError(409, { error: 'a dataset named "customers" already exists in this application' }));
    const { onSaved, onDismiss } = renderModal();
    typeInto('dataset-form-name-input', 'customers');
    await user.type(screen.getByLabelText('Row 1, value'), 'x');
    fireEvent.click(screen.getByTestId('dataset-form-submit'));

    await screen.findByText(/already exists in this application/);
    expect(nameFieldError()).toMatch(/already exists in this application/);
    expect(screen.queryByTestId('dataset-form-server-errors')).toBeNull();
    expect(onSaved).not.toHaveBeenCalled();
    expect(onDismiss).not.toHaveBeenCalled();
  });

  it('lists every server validation error (400 {errors}) in an alert', async () => {
    const user = userEvent.setup();
    const errors = ['repeat_columns must be unique', 'repeat_rows row 1 has 1 cells but 2 cells are expected'];
    datasetsApi.create.mockRejectedValue(httpError(400, { error: errors.join('; '), errors }));
    const { onSaved } = renderModal();
    typeInto('dataset-form-name-input', 'customers');
    await user.type(screen.getByLabelText('Row 1, value'), 'x');
    fireEvent.click(screen.getByTestId('dataset-form-submit'));

    const alert = await screen.findByTestId('dataset-form-server-errors');
    expect(within(alert).getByText(errors[0])).toBeInTheDocument();
    expect(within(alert).getByText(errors[1])).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it('shows the fallback when the server error has no message', async () => {
    const user = userEvent.setup();
    datasetsApi.create.mockRejectedValue({});
    renderModal();
    typeInto('dataset-form-name-input', 'customers');
    await user.type(screen.getByLabelText('Row 1, value'), 'x');
    fireEvent.click(screen.getByTestId('dataset-form-submit'));
    expect(await screen.findByText('Failed to save dataset')).toBeInTheDocument();
  });

  it('Cancel dismisses without saving', () => {
    const { onDismiss, onSaved } = renderModal();
    typeInto('dataset-form-name-input', 'customers');
    fireEvent.click(screen.getByTestId('dataset-form-cancel'));
    expect(onDismiss).toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });
});

describe('DatasetFormModal — edit', () => {
  it('pre-fills name, description and the grid, and PUTs the full replacement', async () => {
    const user = userEvent.setup();
    const saved = { ...EXISTING, name: 'customers-eu', rows: [['a@x.test', 'admin'], ['b@x.test', 'viewer'], ['c@x.test', '']] };
    datasetsApi.update.mockResolvedValue({ dataset: saved });
    const { onSaved } = renderModal(EXISTING);

    expect(screen.getByText('Edit dataset')).toBeInTheDocument();
    expect(screen.getByTestId('dataset-form-submit')).toHaveTextContent('Save');
    expect(screen.getByTestId('dataset-form-name-input').querySelector('input')).toHaveValue('customers');
    expect(screen.getByTestId('dataset-form-description-input').querySelector('textarea')).toHaveValue('Shop customers');
    expect(screen.getByLabelText('Column 2 name')).toHaveValue('role');
    expect(screen.getByLabelText('Row 2, email')).toHaveValue('b@x.test');

    typeInto('dataset-form-name-input', 'customers-eu');
    await user.click(screen.getByRole('button', { name: 'Add row' }));
    await user.type(screen.getByLabelText('Row 3, email'), 'c@x.test');
    fireEvent.click(screen.getByTestId('dataset-form-submit'));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved));
    expect(datasetsApi.update).toHaveBeenCalledWith('app-1', 'ds-1', {
      name: 'customers-eu',
      description: 'Shop customers',
      columns: ['email', 'role'],
      rows: [['a@x.test', 'admin'], ['b@x.test', 'viewer'], ['c@x.test', '']],
    });
    expect(datasetsApi.create).not.toHaveBeenCalled();
  });
});
