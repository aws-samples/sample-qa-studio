/**
 * ImportTemplateModal — secret values for the template's secret steps.
 *
 * Same principle as the JSON import: the modal shows one password field per
 * secret the template needs, and stores the entered values through
 * POST /usecase/{id}/secrets right after the steps were inserted.  Secrets
 * the use case already has are not asked for again.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import ImportTemplateModal from '../ImportTemplateModal';

const apiGet = vi.fn();
const apiPost = vi.fn();
vi.mock('../../../utils/api', () => ({
  api: { get: (...a: unknown[]) => apiGet(...a), post: (...a: unknown[]) => apiPost(...a) },
}));

afterEach(() => cleanup());

const TEMPLATE = { id: 't1', name: 'Login', description: 'd', category: 'c', version: 3 };
const STEPS = [
  { id: 's1', sort: 1, instruction: 'Open login', step_type: 'browser', browser_action: 'navigate' },
  { id: 's2', sort: 2, instruction: 'Click into the username field.', step_type: 'secret', secret_key: 'username' },
  { id: 's3', sort: 3, instruction: 'Click into the password field.', step_type: 'secret', secret_key: 'password' },
];

function mockApi({ existingSecrets = [] as string[], steps = STEPS } = {}) {
  apiGet.mockImplementation(async (path: string) => {
    if (path === 'templates') return { templates: [TEMPLATE] };
    if (path === 'templates/t1/steps') return { steps };
    if (path === 'templates/t1/variables') return { variables: [] };
    if (path === 'usecase/uc-1/secrets') return { secrets: existingSecrets.map((key) => ({ key })) };
    throw new Error(`unexpected GET ${path}`);
  });
  apiPost.mockImplementation(async (path: string) => {
    if (path === 'usecase/uc-1/import-template') return { steps_created: 3, missingSecrets: ['username', 'password'] };
    if (path === 'usecase/uc-1/secrets') return { message: 'ok' };
    throw new Error(`unexpected POST ${path}`);
  });
}

async function renderAndPickTemplate() {
  const user = userEvent.setup();
  const onSuccess = vi.fn();
  render(<ImportTemplateModal visible usecaseId="uc-1" onDismiss={vi.fn()} onSuccess={onSuccess} />);
  await user.click(await screen.findByText('Choose a template'));
  await user.click(await screen.findByRole('option', { name: /Login/ }));
  await screen.findByText('Template Steps Preview (3)');
  return { user, onSuccess };
}

beforeEach(() => {
  apiGet.mockReset();
  apiPost.mockReset();
});

describe('ImportTemplateModal — secrets', () => {
  it('shows a password field for each secret the use case does not have yet', async () => {
    mockApi({ existingSecrets: ['password'] });
    await renderAndPickTemplate();

    const usernameInput = await screen.findByLabelText('username');
    expect(usernameInput).toHaveAttribute('type', 'password');
    expect(screen.queryByLabelText('password')).not.toBeInTheDocument();
    expect(screen.getByText(/already configured on this use case: password/i)).toBeInTheDocument();
  });

  it('imports the steps, then stores the entered secret values', async () => {
    mockApi();
    const { user, onSuccess } = await renderAndPickTemplate();

    await user.type(await screen.findByLabelText('username'), 'qa-user');
    // password left empty on purpose
    await user.click(screen.getByRole('button', { name: 'Import Template' }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    const posts = apiPost.mock.calls.map(([path, body]) => [path, body]);
    expect(posts[0]).toEqual(['usecase/uc-1/import-template', { template_id: 't1', insert_position: -1 }]);
    expect(posts[1]).toEqual(['usecase/uc-1/secrets', { secrets: [{ key: 'username', value: 'qa-user' }] }]);
    expect(posts).toHaveLength(2);
  });

  it('does not call the secrets endpoint when no value was entered', async () => {
    mockApi();
    const { user, onSuccess } = await renderAndPickTemplate();

    await user.click(screen.getByRole('button', { name: 'Import Template' }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(apiPost.mock.calls.map(([path]) => path)).toEqual(['usecase/uc-1/import-template']);
  });

  it('shows no secrets section for templates without secret steps', async () => {
    mockApi({ steps: [STEPS[0]] });
    render(<ImportTemplateModal visible usecaseId="uc-1" onDismiss={vi.fn()} onSuccess={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(await screen.findByText('Choose a template'));
    await user.click(await screen.findByRole('option', { name: /Login/ }));
    await screen.findByText('Template Steps Preview (1)');
    expect(screen.queryByText(/Secrets/)).not.toBeInTheDocument();
  });
});
