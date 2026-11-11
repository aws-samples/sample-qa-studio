/**
 * ApplicationVariablesPage: the shared VariablesEditor on
 * `applications/{id}/variables`, with `readOnly` coming from the shell.
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
vi.mock('../../../utils/api', () => ({
  api: {
    get: (...a: unknown[]) => apiGet(...a),
    post: (...a: unknown[]) => apiPost(...a),
  },
}));

import ApplicationVariablesPage from '../ApplicationVariablesPage';

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

function mockEndpoints(variables: Array<{ key: string; value: string }>) {
  apiGet.mockImplementation((path: string) => {
    if (path === 'applications/app-1') return Promise.resolve(app);
    if (path === 'applications/app-1/variables') return Promise.resolve({ variables });
    return Promise.reject(new Error(`unexpected GET ${path}`));
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/applications/app-1/variables']}>
      <Routes>
        <Route path="/applications/:id/variables" element={<ApplicationVariablesPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  apiGet.mockReset();
  apiPost.mockReset();
  apiPost.mockResolvedValue({});
  mockUsePermissions.mockReset();
  mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'team_lead' }]));
});
afterEach(() => {
  cleanup();
});

describe('ApplicationVariablesPage', () => {
  it('loads the application variables as editable rows and saves them back to the same endpoint', async () => {
    mockEndpoints([{ key: 'base_api', value: 'https://api.staging.example.com' }]);
    renderPage();

    expect(await screen.findByDisplayValue('base_api')).toBeInTheDocument();
    expect(apiGet).toHaveBeenCalledWith('applications/app-1/variables');
    // application rows on their own page carry no source and are plain editable rows
    expect(screen.queryByText('Application')).not.toBeInTheDocument();
    expect(screen.queryByText('Inherited from application')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Add new variable' }));
    fireEvent.change(screen.getByLabelText('Key 2'), { target: { value: 'region' } });
    fireEvent.change(screen.getByLabelText('Value 2'), { target: { value: 'eu-west-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));

    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith('applications/app-1/variables', {
        variables: [
          { key: 'base_api', value: 'https://api.staging.example.com' },
          { key: 'region', value: 'eu-west-1' },
        ],
      }),
    );
    expect(await screen.findByText('Variables saved')).toBeInTheDocument();
  });

  it('renders a read-only table without Save for a user who may not manage the application', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'editor' }]));
    mockEndpoints([{ key: 'base_api', value: 'https://api.staging.example.com' }]);
    renderPage();

    expect(await screen.findByText('base_api')).toBeInTheDocument();
    expect(screen.getByText('https://api.staging.example.com')).toBeInTheDocument();
    expect(screen.getByText(/read-only/)).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Save/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add new variable' })).not.toBeInTheDocument();
  });

  it('shows the empty text when the application has no variables', async () => {
    mockEndpoints([]);
    renderPage();
    expect(await screen.findByText("No variables configured. Click 'Add new variable' to get started.")).toBeInTheDocument();
  });
});
