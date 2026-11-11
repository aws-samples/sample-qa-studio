/**
 * StepFormModal — Repeat step type and child-step behaviour.
 *
 * Cloudscape's Modal renders into a portal; queries go through `screen`.
 * The Autosuggest step-type picker is driven by typing the label and
 * clicking the option.
 */

import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, render, screen, waitFor, within, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import createWrapper from '@cloudscape-design/components/test-utils/dom';

import StepFormModal from '../StepFormModal';

const { datasetsApi } = vi.hoisted(() => ({
  datasetsApi: { get: vi.fn() },
}));

vi.mock('../../../utils/api', () => ({
  api: { get: vi.fn().mockResolvedValue({ secrets: [] }), post: vi.fn() },
  datasetsApi,
}));

afterEach(() => cleanup());
beforeEach(() => { datasetsApi.get.mockReset(); });

const REPEAT_STEP = {
  id: 'r1', sort: 1, step_type: 'repeat', instruction: 'Login as each user',
  repeat_columns: ['email', 'role'], repeat_rows: [['a@x.test', 'admin']],
};

const CUSTOMERS = { dataset_id: 'ds-1', name: 'customers', description: '', column_count: 3, row_count: 5, updated_at: '' };
const LEADS = { dataset_id: 'ds-2', name: 'leads', description: '', column_count: 1, row_count: 2, updated_at: '' };
const DATASETS = [CUSTOMERS, LEADS];

const DATASET_REPEAT_STEP = {
  id: 'r2', sort: 1, step_type: 'repeat', instruction: 'Each customer', dataset_id: 'ds-1',
};

function renderModal(props: Partial<React.ComponentProps<typeof StepFormModal>> = {}) {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  const onDismiss = vi.fn();
  render(
    <StepFormModal
      visible
      onDismiss={onDismiss}
      onSubmit={onSubmit}
      usecaseId="uc-1"
      title="Add Step"
      {...props}
    />,
  );
  return { onSubmit, onDismiss };
}

async function pickStepType(user: ReturnType<typeof userEvent.setup>, label: string) {
  const picker = screen.getByPlaceholderText('Search step types...');
  await user.clear(picker);
  await user.type(picker, label);
  const option = await screen.findByRole('option', { name: new RegExp(`^${label}`) });
  await user.click(option);
}

describe('StepFormModal — Repeat step type', () => {
  it('offers Repeat and shows the dataset editor with a Label field', async () => {
    const user = userEvent.setup();
    renderModal();
    await pickStepType(user, 'Repeat');
    expect(screen.getByText('Label')).toBeInTheDocument();
    expect(screen.getByTestId('repeat-dataset-grid')).toBeInTheDocument();
    // Other type-specific fields are hidden.
    expect(screen.queryByText('Browser Action')).not.toBeInTheDocument();
    expect(screen.queryByText('Runtime Variable')).not.toBeInTheDocument();
  });

  it('submits step_type, label, columns and rows', async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderModal();
    await pickStepType(user, 'Repeat');
    await user.type(screen.getByPlaceholderText('Login as each user'), 'Login as each user');
    await user.clear(screen.getByLabelText('Column 1 name'));
    await user.type(screen.getByLabelText('Column 1 name'), 'email');
    await user.type(screen.getByLabelText('Row 1, email'), 'a@x.test');
    await user.click(screen.getByRole('button', { name: 'Create Step' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.step_type).toBe('repeat');
    expect(payload.instruction).toBe('Login as each user');
    expect(payload.repeat_columns).toEqual(['email']);
    expect(payload.repeat_rows).toEqual([['a@x.test']]);
    expect(payload.parent_step_id).toBeUndefined();
  });

  it('disables Save while the dataset is invalid', async () => {
    const user = userEvent.setup();
    renderModal();
    await pickStepType(user, 'Repeat');
    await user.type(screen.getByPlaceholderText('Login as each user'), 'L');
    await user.clear(screen.getByLabelText('Column 1 name'));
    await user.type(screen.getByLabelText('Column 1 name'), 'UniqueID');
    expect(screen.getByText(/is a reserved name/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create Step' })).toBeDisabled();
  });

  it('pre-fills the grid when editing an existing repeat', () => {
    renderModal({ step: REPEAT_STEP, title: 'Edit Step' });
    expect(screen.getByLabelText('Column 1 name')).toHaveValue('email');
    expect(screen.getByLabelText('Column 2 name')).toHaveValue('role');
    expect(screen.getByLabelText('Row 1, role')).toHaveValue('admin');
    expect(screen.getByDisplayValue('Login as each user')).toBeInTheDocument();
  });

  it('is not offered when allowRepeat is false (templates)', async () => {
    const user = userEvent.setup();
    renderModal({ allowRepeat: false });
    const picker = screen.getByPlaceholderText('Search step types...');
    await user.type(picker, 'Repeat');
    expect(screen.queryByRole('option', { name: /^Repeat/ })).not.toBeInTheDocument();
  });
});

/** The Dataset source radio group; null when the control is not rendered. */
const sourceGroup = () => createWrapper(document.body).findRadioGroup('[data-testid="repeat-source"]');
const sourceInput = (value: 'inline' | 'application') => sourceGroup()!.findInputByValue(value)!.getElement();
const datasetSelect = () => createWrapper(document.body).findSelect('[data-testid="repeat-dataset-select"]')!;

describe('StepFormModal — Repeat dataset source', () => {
  it('defaults to Inline for a new step and shows the grid', async () => {
    const user = userEvent.setup();
    renderModal({ applicationId: 'app-1', datasets: DATASETS });
    await pickStepType(user, 'Repeat');
    expect(sourceInput('inline')).toBeChecked();
    expect(sourceInput('application')).not.toBeChecked();
    expect(screen.getByTestId('repeat-dataset-grid')).toBeInTheDocument();
    expect(screen.queryByTestId('repeat-dataset-select')).not.toBeInTheDocument();
  });

  it('derives Application dataset from dataset_id when editing and pre-selects it', () => {
    renderModal({ step: DATASET_REPEAT_STEP, title: 'Edit Step', applicationId: 'app-1', datasets: DATASETS });
    expect(sourceInput('application')).toBeChecked();
    expect(screen.queryByTestId('repeat-dataset-grid')).not.toBeInTheDocument();
    expect(datasetSelect().findTrigger().getElement()).toHaveTextContent('customers');
  });

  it('derives Inline when editing a step with inline rows', () => {
    renderModal({ step: REPEAT_STEP, title: 'Edit Step', applicationId: 'app-1', datasets: DATASETS });
    expect(sourceInput('inline')).toBeChecked();
    expect(screen.getByLabelText('Column 1 name')).toHaveValue('email');
  });

  it('lists the application datasets with columns × rows and submits dataset_id without inline fields', async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderModal({ applicationId: 'app-1', datasets: DATASETS });
    await pickStepType(user, 'Repeat');
    await user.type(screen.getByPlaceholderText('Login as each user'), 'Each customer');
    await user.click(sourceInput('application'));

    // Save needs a dataset.
    expect(screen.getByRole('button', { name: 'Create Step' })).toBeDisabled();

    act(() => datasetSelect().openDropdown());
    const options = datasetSelect().findDropdown().findOptions();
    expect(options.map((o) => o.getElement().textContent)).toEqual([
      expect.stringContaining('customers'),
      expect.stringContaining('leads'),
    ]);
    expect(options[0].getElement()).toHaveTextContent('3 columns × 5 rows');
    act(() => datasetSelect().selectOptionByValue('ds-2'));

    await user.click(screen.getByRole('button', { name: 'Create Step' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.step_type).toBe('repeat');
    expect(payload.dataset_id).toBe('ds-2');
    // Views merge the payload over the stored step; the inline side must
    // not survive that merge (JSON drops undefined), so it is set explicitly.
    expect('repeat_columns' in payload).toBe(true);
    expect(payload.repeat_columns).toBeUndefined();
    expect(payload.repeat_rows).toBeUndefined();
  });

  it('inline submit carries the grid and no dataset_id', async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderModal({ applicationId: 'app-1', datasets: DATASETS });
    await pickStepType(user, 'Repeat');
    await user.type(screen.getByPlaceholderText('Login as each user'), 'Login as each user');
    await user.clear(screen.getByLabelText('Column 1 name'));
    await user.type(screen.getByLabelText('Column 1 name'), 'email');
    await user.type(screen.getByLabelText('Row 1, email'), 'a@x.test');
    await user.click(screen.getByRole('button', { name: 'Create Step' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.repeat_columns).toEqual(['email']);
    expect(payload.repeat_rows).toEqual([['a@x.test']]);
    expect('dataset_id' in payload).toBe(true);
    expect(payload.dataset_id).toBeUndefined();
  });

  it('switching an application-backed step to Inline drops dataset_id and starts an empty grid', async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderModal({ step: DATASET_REPEAT_STEP, title: 'Edit Step', applicationId: 'app-1', datasets: DATASETS });
    await user.click(sourceInput('inline'));
    expect(screen.getByTestId('repeat-dataset-grid')).toBeInTheDocument();
    // Empty grid: the default single column/row.
    expect(screen.getByLabelText('Column 1 name')).toHaveValue('value');
    await user.type(screen.getByLabelText('Row 1, value'), '1');
    await user.click(screen.getByRole('button', { name: 'Update Step' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.dataset_id).toBeUndefined();
    expect(payload.repeat_columns).toEqual(['value']);
    expect(payload.repeat_rows).toEqual([['1']]);
  });

  it('switching an inline step to Application dataset clears the grid and requires a selection', async () => {
    const user = userEvent.setup();
    renderModal({ step: REPEAT_STEP, title: 'Edit Step', applicationId: 'app-1', datasets: DATASETS });
    await user.click(sourceInput('application'));
    expect(screen.getByRole('button', { name: 'Update Step' })).toBeDisabled();
    expect(datasetSelect().findTrigger().getElement()).not.toHaveTextContent('customers');
    // Back to inline: the previous rows are gone.
    await user.click(sourceInput('inline'));
    expect(screen.getByLabelText('Column 1 name')).toHaveValue('value');
    expect(screen.queryByLabelText('Column 2 name')).not.toBeInTheDocument();
  });

  it('links to the application datasets page when there are none', async () => {
    const user = userEvent.setup();
    renderModal({ applicationId: 'app-1', datasets: [] });
    await pickStepType(user, 'Repeat');
    await user.click(sourceInput('application'));
    act(() => datasetSelect().openDropdown());
    const link = await screen.findByRole('link', { name: /Datasets page/ });
    expect(link).toHaveAttribute('href', '/applications/app-1/datasets');
  });

  it('hides the control without an application (templates, unassigned use cases)', async () => {
    const user = userEvent.setup();
    renderModal();
    await pickStepType(user, 'Repeat');
    expect(sourceGroup()).toBeNull();
    expect(screen.getByTestId('repeat-dataset-grid')).toBeInTheDocument();
  });

  it('is absent when allowRepeat is false even with an application', () => {
    renderModal({ allowRepeat: false, applicationId: 'app-1', datasets: DATASETS, step: { ...REPEAT_STEP, step_type: 'navigation' } });
    expect(sourceGroup()).toBeNull();
  });
});

describe('StepFormModal — child of a repeat', () => {
  it('hides Repeat, shows the Inside hint and includes parent_step_id in the payload', async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderModal({ parentStepId: 'r1', existingSteps: [REPEAT_STEP] });
    expect(screen.getByTestId('inside-repeat-hint')).toHaveTextContent('Inside: Login as each user');
    expect(screen.getByTestId('inside-repeat-hint')).toHaveTextContent('{{email}}, {{role}}');

    const picker = screen.getByPlaceholderText('Search step types...');
    await user.type(picker, 'Repeat');
    expect(screen.queryByRole('option', { name: /^Repeat/ })).not.toBeInTheDocument();
    await user.clear(picker);

    await user.type(screen.getByPlaceholderText('Enter navigation instruction'), 'Type {{email}}');
    await user.click(screen.getByRole('button', { name: 'Create Step' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].parent_step_id).toBe('r1');
    expect(onSubmit.mock.calls[0][0].step_type).toBe('navigation');
  });

  it('editing a child keeps parent_step_id', async () => {
    const user = userEvent.setup();
    const child = { id: 'c1', sort: 2, step_type: 'navigation', instruction: 'Type {{email}}', parent_step_id: 'r1' };
    const { onSubmit } = renderModal({ step: child, existingSteps: [REPEAT_STEP, child], title: 'Edit Step' });
    await user.click(screen.getByRole('button', { name: 'Update Step' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].parent_step_id).toBe('r1');
  });

  it('assertion child lists the parent dataset columns as variables', async () => {
    const user = userEvent.setup();
    const captured = { id: 'v1', sort: 0, step_type: 'retrieve_value', instruction: 'Get title', capture_variable: 'title' };
    renderModal({ parentStepId: 'r1', existingSteps: [captured, REPEAT_STEP] });
    await pickStepType(user, 'Assertion');
    await user.click(screen.getByRole('button', { name: /Select a variable or dataset column/ }));
    const listbox = await screen.findByRole('listbox');
    expect(within(listbox).getByText('From dataset: Login as each user')).toBeInTheDocument();
    expect(within(listbox).getByText('email')).toBeInTheDocument();
    expect(within(listbox).getByText('role')).toBeInTheDocument();
    expect(within(listbox).getByText('title')).toBeInTheDocument();
  });

  it('top-level assertion sees only captured variables', async () => {
    const user = userEvent.setup();
    const captured = { id: 'v1', sort: 0, step_type: 'retrieve_value', instruction: 'Get title', capture_variable: 'title' };
    renderModal({ existingSteps: [captured, REPEAT_STEP] });
    await pickStepType(user, 'Assertion');
    await user.click(screen.getByRole('button', { name: /Select a runtime variable/ }));
    const listbox = await screen.findByRole('listbox');
    expect(within(listbox).queryByText(/From dataset/)).not.toBeInTheDocument();
    expect(within(listbox).getByText('title')).toBeInTheDocument();
  });
});

describe('StepFormModal — child of a dataset-backed repeat', () => {
  const CUSTOMERS_FULL = {
    ...CUSTOMERS, columns: ['first_name', 'last_name', 'email'], rows: [['A', 'B', 'a@x.test']], created_at: '', created_by: '',
  };

  it('fetches the dataset once and offers its columns in the hint and as variables', async () => {
    const user = userEvent.setup();
    datasetsApi.get.mockResolvedValue({ dataset: CUSTOMERS_FULL });
    renderModal({ parentStepId: 'r2', existingSteps: [DATASET_REPEAT_STEP], applicationId: 'app-1', datasets: DATASETS });
    await waitFor(() => expect(datasetsApi.get).toHaveBeenCalledWith('app-1', 'ds-1'));
    await waitFor(() =>
      expect(screen.getByTestId('inside-repeat-hint')).toHaveTextContent('{{first_name}}, {{last_name}}, {{email}}'),
    );
    expect(datasetsApi.get).toHaveBeenCalledTimes(1);

    await pickStepType(user, 'Assertion');
    await user.click(screen.getByRole('button', { name: /Select a variable or dataset column/ }));
    const listbox = await screen.findByRole('listbox');
    expect(within(listbox).getByText('From dataset: Each customer')).toBeInTheDocument();
    expect(within(listbox).getByText('first_name')).toBeInTheDocument();
    expect(within(listbox).getByText('email')).toBeInTheDocument();
  });

  it('shows the hint without columns when the dataset cannot be loaded', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    datasetsApi.get.mockRejectedValue(new Error('boom'));
    renderModal({ parentStepId: 'r2', existingSteps: [DATASET_REPEAT_STEP], applicationId: 'app-1', datasets: DATASETS });
    await waitFor(() => expect(datasetsApi.get).toHaveBeenCalled());
    await waitFor(() => expect(error).toHaveBeenCalled());
    expect(screen.getByTestId('inside-repeat-hint')).toHaveTextContent('Inside: Each customer');
    expect(screen.getByTestId('inside-repeat-hint')).not.toHaveTextContent('{{');
    error.mockRestore();
  });

  it('does not fetch for an inline parent', () => {
    renderModal({ parentStepId: 'r1', existingSteps: [REPEAT_STEP], applicationId: 'app-1', datasets: DATASETS });
    expect(screen.getByTestId('inside-repeat-hint')).toHaveTextContent('{{email}}, {{role}}');
    expect(datasetsApi.get).not.toHaveBeenCalled();
  });
});

describe('Wizard StepForm', () => {
  it('does not offer the Repeat step type', async () => {
    const source = await import('../../wizard/StepForm?raw');
    expect(source.default).not.toMatch(/value:\s*'repeat'/);
  });
});
