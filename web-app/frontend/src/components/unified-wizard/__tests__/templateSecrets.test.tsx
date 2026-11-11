/**
 * Unified wizard — "Start from template" asks for the template's secrets.
 *
 * `POST /templates/{id}/apply` answers with `missingSecrets` for the secret
 * steps it copied.  The review step then shows the same "Configure secrets"
 * form the JSON import uses and stores the values via
 * POST /usecase/{id}/secrets.  Keys the owning application already provides
 * (`GET /usecase/{id}/secrets` rows with `source: "application"`) are not
 * asked for — the server falls back to the application secret at run time.
 */
import { useReducer } from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

import ReviewAndCreateStep from '../steps/ReviewAndCreateStep';
import { initialWizardState, wizardReducer } from '../wizardReducer';
import type { WizardState } from '../types';

const apiPost = vi.fn();
const apiGet = vi.fn();
const navigate = vi.fn();
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));
vi.mock('../../../utils/api', () => ({
  api: { post: (...a: unknown[]) => apiPost(...a), get: (...a: unknown[]) => apiGet(...a) },
  exportImportApi: { importUsecase: vi.fn() },
  devicesApi: { list: vi.fn().mockResolvedValue({ devices: [] }) },
}));

let consoleError: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
});
afterEach(() => {
  cleanup();
  consoleError.mockRestore();
});

function templateState(): WizardState {
  return {
    ...initialWizardState,
    creationPath: 'create-new',
    creationMethod: 'template',
    basicInfo: { ...initialWizardState.basicInfo, name: 'Login copy', startingUrl: 'https://e.test/' },
    templateConfig: { ...initialWizardState.templateConfig, selectedTemplateId: 't1' },
  };
}

/** Drives the step with the real reducer so dispatched state re-renders. */
function Harness({ submitTrigger }: { submitTrigger: number }) {
  const [state, dispatch] = useReducer(wizardReducer, templateState());
  return <ReviewAndCreateStep state={state} dispatch={dispatch} validationErrors={{}} submitTrigger={submitTrigger} />;
}

async function submit() {
  const { rerender } = render(<Harness submitTrigger={0} />);
  rerender(<Harness submitTrigger={1} />);
  await waitFor(() => expect(apiPost).toHaveBeenCalled());
}

describe('unified wizard — template secrets', () => {
  beforeEach(() => {
    apiPost.mockReset();
    apiGet.mockReset();
    // The new use case has no secrets of its own yet and no inherited ones.
    apiGet.mockResolvedValue({ secrets: [] });
    navigate.mockReset();
  });

  it('shows the secrets form when apply reports missing secrets, then stores the values', async () => {
    apiPost.mockImplementation(async (path: string) => {
      if (path === 'templates/t1/apply') return { success: true, usecaseId: 'uc-new', missingSecrets: ['username', 'password'] };
      if (path === 'usecase/uc-new/secrets') return { message: 'ok' };
      throw new Error(`unexpected POST ${path}`);
    });
    await submit();

    expect(await screen.findByText('Configure secrets')).toBeInTheDocument();
    expect(apiGet).toHaveBeenCalledWith('usecase/uc-new/secrets');
    expect(navigate).not.toHaveBeenCalled();
    expect(screen.queryByTestId('inherited-secrets-hint')).not.toBeInTheDocument();
    const user = userEvent.setup();
    const username = screen.getByLabelText('username');
    expect(username).toHaveAttribute('type', 'password');
    await user.type(username, 'qa-user');
    await user.type(screen.getByLabelText('password'), 'pw');
    await user.click(screen.getByRole('button', { name: 'Save secrets' }));

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/usecase/uc-new'));
    expect(apiPost.mock.calls[1]).toEqual([
      'usecase/uc-new/secrets',
      { secrets: [{ key: 'username', value: 'qa-user' }, { key: 'password', value: 'pw' }] },
    ]);
  });

  it('does not ask for keys the application already provides, and says so', async () => {
    apiPost.mockImplementation(async (path: string) => {
      if (path === 'templates/t1/apply') return { success: true, usecaseId: 'uc-new', missingSecrets: ['username', 'password'] };
      if (path === 'usecase/uc-new/secrets') return { message: 'ok' };
      throw new Error(`unexpected POST ${path}`);
    });
    apiGet.mockResolvedValue({ secrets: [{ key: 'password', secret_name: 'n', created_at: 't', source: 'application' }] });
    await submit();

    expect(await screen.findByText('Configure secrets')).toBeInTheDocument();
    expect(screen.getByLabelText('username')).toBeInTheDocument();
    expect(screen.queryByLabelText('password')).not.toBeInTheDocument();
    expect(screen.getByTestId('inherited-secrets-hint')).toHaveTextContent(
      'password is inherited from the application and already has a value. Add a use case secret with the same key on the Secrets tab to override it.',
    );

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('username'), 'qa-user');
    await user.click(screen.getByRole('button', { name: 'Save secrets' }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/usecase/uc-new'));
    expect(apiPost.mock.calls[1]).toEqual(['usecase/uc-new/secrets', { secrets: [{ key: 'username', value: 'qa-user' }] }]);
  });

  it('skips the form entirely when every missing key is inherited from the application', async () => {
    apiPost.mockResolvedValue({ success: true, usecaseId: 'uc-new', missingSecrets: ['username', 'password'] });
    apiGet.mockResolvedValue({
      secrets: [
        { key: 'username', source: 'application' },
        { key: 'password', source: 'application' },
      ],
    });
    await submit();
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/usecase/uc-new'));
    expect(screen.queryByText('Configure secrets')).not.toBeInTheDocument();
    expect(apiPost).toHaveBeenCalledTimes(1);
  });

  it('falls back to asking for every key when the secret list cannot be loaded', async () => {
    apiPost.mockResolvedValue({ success: true, usecaseId: 'uc-new', missingSecrets: ['username', 'password'] });
    apiGet.mockRejectedValue(new Error('boom'));
    await submit();
    expect(await screen.findByText('Configure secrets')).toBeInTheDocument();
    expect(screen.getByLabelText('username')).toBeInTheDocument();
    expect(screen.getByLabelText('password')).toBeInTheDocument();
    expect(screen.queryByTestId('inherited-secrets-hint')).not.toBeInTheDocument();
    expect(consoleError).toHaveBeenCalled();
  });

  it('"Skip for now" opens the use case without storing anything', async () => {
    apiPost.mockResolvedValue({ success: true, usecaseId: 'uc-new', missingSecrets: ['username'] });
    await submit();
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Skip for now' }));
    expect(navigate).toHaveBeenCalledWith('/usecase/uc-new');
    expect(apiPost).toHaveBeenCalledTimes(1);
  });

  it('navigates straight to the use case when no secrets are missing', async () => {
    apiPost.mockResolvedValue({ success: true, usecaseId: 'uc-new' });
    await submit();
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/usecase/uc-new'));
    expect(screen.queryByText('Configure secrets')).not.toBeInTheDocument();
    expect(apiGet).not.toHaveBeenCalled();
  });
});
