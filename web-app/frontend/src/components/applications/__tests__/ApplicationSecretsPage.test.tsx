/**
 * ApplicationSecretsPage — KeyValueManager on `applications/{id}/secrets`:
 * lists keys only, saves/deletes on the application route, and is list-only
 * for users who cannot manage the application.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockUsePermissions = vi.fn();
vi.mock('../../../auth', async () => {
  const access = await vi.importActual<typeof import('../../../auth/applicationAccess')>('../../../auth/applicationAccess');
  return { ...access, usePermissions: () => mockUsePermissions() };
});

const apiGet = vi.fn();
const apiPost = vi.fn();
const apiDelete = vi.fn();
vi.mock('../../../utils/api', () => ({
  api: {
    get: (...a: unknown[]) => apiGet(...a),
    post: (...a: unknown[]) => apiPost(...a),
    delete: (...a: unknown[]) => apiDelete(...a),
  },
}));

import ApplicationSecretsPage from '../ApplicationSecretsPage';

const perms = (isAdmin: boolean, teams: Array<{ team_id: string; role: string }>) => ({
  isAdmin,
  isTeamLead: teams.some((t) => t.role === 'team_lead'),
  teams: teams.map((t) => ({ ...t, group_name: `team-${t.team_id}-${t.role}` })),
  hasScope: () => true,
  scopes: [],
  isLoading: false,
});

const app = { id: 'app-1', name: 'Shop', base_url: 'https://shop.test', description: '', team: 'A',
  owner_team_id: 'team-a', environments: [] };

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/applications/app-1/secrets']}>
      <Routes>
        <Route path="/applications/:id/secrets" element={<ApplicationSecretsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function mockApi(secrets: Array<{ key: string }>) {
  apiGet.mockImplementation(async (path: string) => {
    if (path === 'applications/app-1') return app;
    if (path === 'applications/app-1/secrets') return { secrets };
    throw new Error(`unexpected GET ${path}`);
  });
}

beforeEach(() => {
  apiGet.mockReset();
  apiPost.mockReset();
  apiDelete.mockReset();
  apiPost.mockResolvedValue({ created: 1, updated: 0 });
  apiDelete.mockResolvedValue(undefined);
  mockUsePermissions.mockReset();
  mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'team_lead' }]));
});
afterEach(() => {
  cleanup();
});

describe('ApplicationSecretsPage', () => {
  it('lists the application secret keys without a value column or badges', async () => {
    mockApi([{ key: 'admin_password', secret_name: 'n', created_at: 't' } as { key: string }]);
    renderPage();
    expect(await screen.findByText('admin_password')).toBeInTheDocument();
    expect(apiGet).toHaveBeenCalledWith('applications/app-1/secrets');
    expect(screen.queryByRole('columnheader', { name: 'Secret Value' })).not.toBeInTheDocument();
    expect(screen.queryByText('Application')).not.toBeInTheDocument();
    expect(screen.getByText(/use case secret with the same key takes precedence/)).toBeInTheDocument();
  });

  it('shows the application empty text', async () => {
    mockApi([]);
    renderPage();
    expect(await screen.findByText('No secrets configured for this application.')).toBeInTheDocument();
  });

  it('saves a new secret on the application route and never shows the value again', async () => {
    mockApi([]);
    const { container } = renderPage();
    await screen.findByText('No secrets configured for this application.');

    fireEvent.click(screen.getByRole('button', { name: 'Add new secret' }));
    fireEvent.change(screen.getByLabelText('Secret Key 1'), { target: { value: 'admin_password' } });
    fireEvent.change(screen.getByLabelText('Secret Value 1'), { target: { value: 'hunter2-app' } });
    mockApi([{ key: 'admin_password' }]);
    fireEvent.click(screen.getByRole('button', { name: 'Save Secrets' }));

    expect(await screen.findByText('Secrets saved successfully')).toBeInTheDocument();
    expect(apiPost).toHaveBeenCalledWith('applications/app-1/secrets', {
      secrets: [{ key: 'admin_password', value: 'hunter2-app' }],
    });
    expect(await screen.findByText('admin_password')).toBeInTheDocument();
    expect(container.innerHTML).not.toContain('hunter2-app');
  });

  it('deletes a secret on the application route', async () => {
    mockApi([{ key: 'admin_password' }]);
    renderPage();
    await screen.findByText('admin_password');
    mockApi([]);
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(await screen.findByText('Secret "admin_password" deleted successfully')).toBeInTheDocument();
    expect(apiDelete).toHaveBeenCalledWith('applications/app-1/secrets', { secret_key: 'admin_password' });
    await waitFor(() => expect(screen.queryByText('admin_password')).not.toBeInTheDocument());
  });

  it('is list-only for a user who cannot manage the application', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'editor' }]));
    mockApi([{ key: 'admin_password' }]);
    renderPage();
    expect(await screen.findByText('admin_password')).toBeInTheDocument();
    expect(screen.getByText(/read-only/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save Secrets' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add new secret' })).not.toBeInTheDocument();
  });
});
