import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import TeamDetailPage from '../TeamDetailPage';

// Mock api
vi.mock('../../../utils/api', () => ({
  api: {
    get: vi.fn(),
    delete: vi.fn(),
  },
}));

import { api } from '../../../utils/api';
const mockGet = vi.mocked(api.get);
const mockDelete = vi.mocked(api.delete);

// Mock hooks
vi.mock('../../../hooks/useTeamMembers', () => ({
  useTeamMembers: () => ({
    members: [
      { userId: 'user-1', email: 'alice@example.com', role: 'editor', joinedAt: '2024-01-01' },
    ],
    loading: false,
    fetchMembers: vi.fn(),
    addMember: vi.fn(),
    removeMember: vi.fn(),
    changeRole: vi.fn(),
  }),
}));

vi.mock('../../../hooks/useSharedAccess', () => ({
  useSharedAccess: () => ({
    grants: [
      { grantId: 'g-1', targetTeamId: 'team-2', targetTeamName: 'Beta', accessLevel: 'view', grantedAt: '2024-01-01' },
    ],
    loading: false,
    fetchGrants: vi.fn(),
    grantAccess: vi.fn(),
    revokeAccess: vi.fn(),
  }),
}));

vi.mock('../../../hooks/useTeams', () => ({
  useTeams: () => ({
    teams: [{ id: 'team-2', name: 'Beta', memberCount: 2, applicationCount: 1 }],
    loading: false,
    error: null,
    fetchTeams: vi.fn(),
    createTeam: vi.fn(),
    deleteTeam: vi.fn(),
  }),
}));

vi.mock('../../../hooks/useApplications', () => ({
  useApplications: () => ({
    applications: [],
    options: [],
    loading: false,
  }),
}));

const mockUsePermissions = vi.fn();
vi.mock('../../../auth', () => ({
  usePermissions: () => mockUsePermissions(),
}));

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

function renderPage(teamId: string = 'team-1') {
  return render(
    <MemoryRouter initialEntries={[`/admin/teams/${teamId}`]}>
      <Routes>
        <Route path="/admin/teams/:id" element={<TeamDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('TeamDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUsePermissions.mockReturnValue({
      isAdmin: true,
      isTeamLead: true,
      hasScope: () => true,
      teams: [{ team_id: 'team-1', role: 'admin', group_name: 'team-team-1-admin' }],
      scopes: [],
      isLoading: false,
    });
    mockGet.mockResolvedValue({
      id: 'team-1',
      name: 'Alpha Team',
      memberCount: 3,
      applicationCount: 2,
      created_by: 'admin-user',
      created_at: '2024-01-01',
    });
  });

  it('renders team detail with tabs', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getAllByText('Alpha Team').length).toBeGreaterThan(0);
    });

    // Tab labels might appear multiple times (tab + tab content header)
    expect(screen.getAllByText('Members').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Applications').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Shared Access').length).toBeGreaterThan(0);
  });

  it('shows members in the members tab', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getAllByText('Alpha Team').length).toBeGreaterThan(0);
    });

    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
  });

  it('shows shared access grants', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getAllByText('Alpha Team').length).toBeGreaterThan(0);
    });

    // Click Shared Access tab
    fireEvent.click(screen.getByText('Shared Access'));

    await waitFor(() => {
      expect(screen.getByText('Beta')).toBeInTheDocument();
    });
  });

  it('shows delete button for admin', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('delete-team-button')).toBeInTheDocument();
    });
  });

  it('hides delete button for non-admin', async () => {
    mockUsePermissions.mockReturnValue({
      isAdmin: false,
      isTeamLead: true,
      hasScope: () => false,
      teams: [{ team_id: 'team-1', role: 'team_lead', group_name: 'team-team-1-team_lead' }],
      scopes: [],
      isLoading: false,
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getAllByText('Alpha Team').length).toBeGreaterThan(0);
    });

    expect(screen.queryByTestId('delete-team-button')).not.toBeInTheDocument();
  });

  it('opens delete confirmation modal', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('delete-team-button')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('delete-team-button'));

    await waitFor(() => {
      expect(screen.getByText(/This action cannot be undone/)).toBeInTheDocument();
    });
  });
});
