/**
 * StepFormModal — Secret step: the dropdown lists the use case's effective
 * secrets (own + inherited application secrets, labelled "(application)"),
 * the saved `secret_key` is the bare key, and inline creation may override an
 * inherited key but not duplicate an own one.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const apiGet = vi.fn();
const apiPost = vi.fn();
vi.mock('../../../utils/api', () => ({
  api: { get: (...a: unknown[]) => apiGet(...a), post: (...a: unknown[]) => apiPost(...a) },
}));

import StepFormModal from '../StepFormModal';

const SECRETS = [
  { key: 'password', description: 'Login password', source: 'usecase' },
  { key: 'admin_password', description: 'Admin', source: 'application' },
];

beforeEach(() => {
  apiGet.mockReset();
  apiPost.mockReset();
  apiGet.mockResolvedValue({ secrets: SECRETS });
  apiPost.mockResolvedValue({ message: 'ok' });
});
afterEach(() => {
  cleanup();
});

function renderModal(props: Partial<React.ComponentProps<typeof StepFormModal>> = {}) {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  render(
    <StepFormModal visible onDismiss={vi.fn()} onSubmit={onSubmit} usecaseId="uc-1" title="Add Step" {...props} />,
  );
  return { onSubmit };
}

async function pickSecretType(user: ReturnType<typeof userEvent.setup>) {
  const picker = screen.getByPlaceholderText('Search step types...');
  await user.clear(picker);
  await user.type(picker, 'Secret');
  await user.click(await screen.findByRole('option', { name: /^Secret/ }));
  await waitFor(() => expect(apiGet).toHaveBeenCalledWith('usecase/uc-1/secrets'));
}

async function openSecretDropdown(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /Select a secret/ }));
  return screen.findByRole('listbox');
}

describe('StepFormModal — secret step', () => {
  it('lists own and inherited secrets, suffixing inherited ones with (application)', async () => {
    const user = userEvent.setup();
    renderModal();
    await pickSecretType(user);
    const listbox = await openSecretDropdown(user);
    expect(within(listbox).getByText('password')).toBeInTheDocument();
    expect(within(listbox).getByText('admin_password (application)')).toBeInTheDocument();
    expect(within(listbox).getByText('Admin')).toBeInTheDocument();
  });

  it('saves the bare key as secret_key when an inherited secret is picked', async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderModal();
    await pickSecretType(user);
    await user.type(screen.getByPlaceholderText('Describe the action with the secret'), 'Type the admin password');
    const listbox = await openSecretDropdown(user);
    await user.click(within(listbox).getByText('admin_password (application)'));
    expect(screen.getByRole('button', { name: /admin_password \(application\)/ })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Create Step' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ step_type: 'secret', secret_key: 'admin_password' });
  });

  it('shows the inherited label for an existing step that references an application secret', async () => {
    renderModal({
      step: { id: 's1', sort: 1, step_type: 'secret', instruction: 'Type it', secret_key: 'admin_password' },
      title: 'Edit Step',
    });
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('usecase/uc-1/secrets'));
    expect(await screen.findByRole('button', { name: /admin_password \(application\)/ })).toBeInTheDocument();
  });

  it('inline creation refuses to duplicate an own key but may override an inherited one', async () => {
    const user = userEvent.setup();
    renderModal();
    await pickSecretType(user);
    await user.click(screen.getByRole('button', { name: 'Add Secret' }));

    await user.type(screen.getByPlaceholderText('e.g., api_key, password, token'), 'password');
    await user.type(screen.getByPlaceholderText('Enter the secret value'), 'v');
    await user.click(screen.getByRole('button', { name: 'Create' }));
    expect(await screen.findByText('Secret "password" already exists')).toBeInTheDocument();
    expect(apiPost).not.toHaveBeenCalled();

    const keyInput = screen.getByPlaceholderText('e.g., api_key, password, token');
    await user.clear(keyInput);
    await user.type(keyInput, 'admin_password');
    apiGet.mockResolvedValue({ secrets: [...SECRETS.filter((s) => s.source === 'usecase'), { key: 'admin_password', source: 'usecase' }] });
    await user.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith('usecase/uc-1/secrets', { secrets: [{ key: 'admin_password', value: 'v' }] }),
    );
    // After the override the row is an own secret: plain label.
    const trigger = await screen.findByRole('button', { name: /admin_password/ });
    expect(trigger).not.toHaveTextContent('(application)');
    expect(screen.queryByText('Secret "password" already exists')).not.toBeInTheDocument();
  });
});

describe('Wizard StepForm — secret step', () => {
  async function renderStepForm(selectedSecret = '') {
    const { default: StepForm } = await import('../../wizard/StepForm');
    const onSelectedSecretChange = vi.fn();
    render(
      <StepForm
        usecaseId="uc-1"
        stepType="secret"
        instruction=""
        selectedSecret={selectedSecret}
        validationType="bool"
        validationOperator="exact"
        validationValue=""
        captureVariable=""
        valueType="string"
        assertionVariable=""
        booleanInputMode="true"
        onStepTypeChange={vi.fn()}
        onInstructionChange={vi.fn()}
        onSelectedSecretChange={onSelectedSecretChange}
        onValidationTypeChange={vi.fn()}
        onValidationOperatorChange={vi.fn()}
        onValidationValueChange={vi.fn()}
        onCaptureVariableChange={vi.fn()}
        onValueTypeChange={vi.fn()}
        onAssertionVariableChange={vi.fn()}
        onBooleanInputModeChange={vi.fn()}
      />,
    );
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('usecase/uc-1/secrets'));
    return { onSelectedSecretChange };
  }

  it('labels inherited secrets and reports the bare key on selection', async () => {
    const user = userEvent.setup();
    const { onSelectedSecretChange } = await renderStepForm();
    const listbox = await openSecretDropdown(user);
    expect(within(listbox).getByText('password')).toBeInTheDocument();
    await user.click(within(listbox).getByText('admin_password (application)'));
    expect(onSelectedSecretChange).toHaveBeenCalledWith('admin_password');
  });

  it('shows the inherited label for the current selection', async () => {
    await renderStepForm('admin_password');
    expect(await screen.findByRole('button', { name: /admin_password \(application\)/ })).toBeInTheDocument();
  });
});
