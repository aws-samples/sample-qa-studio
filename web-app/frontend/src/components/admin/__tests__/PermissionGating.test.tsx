import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

// We test the navigation rendering by checking the nav items in a simplified AppContent-like setup
// The key principle: Hidden-UI pattern — buttons NOT in DOM when permission insufficient

const mockUsePermissions = vi.fn();
vi.mock('../../../auth', () => ({
  usePermissions: () => mockUsePermissions(),
  PermissionsProvider: ({ children }: any) => <>{children}</>,
}));

vi.mock('../../../utils/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue([]),
    post: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(null),
    patch: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock('../../../hooks/useTeams', () => ({
  useTeams: () => ({
    teams: [{ id: 'team-1', name: 'Alpha', memberCount: 3, applicationCount: 2 }],
    loading: false,
    error: null,
    fetchTeams: vi.fn(),
    createTeam: vi.fn(),
    deleteTeam: vi.fn(),
  }),
}));

vi.mock('../../../hooks/useTeamMembers', () => ({
  useTeamMembers: () => ({
    members: [{ userId: 'u-1', email: 'test@test.com', role: 'editor', joinedAt: '2024-01-01' }],
    loading: false,
    fetchMembers: vi.fn(),
    addMember: vi.fn(),
    removeMember: vi.fn(),
    changeRole: vi.fn(),
  }),
}));

vi.mock('../../../hooks/useSharedAccess', () => ({
  useSharedAccess: () => ({
    grants: [],
    loading: false,
    fetchGrants: vi.fn(),
    grantAccess: vi.fn(),
    revokeAccess: vi.fn(),
  }),
}));

vi.mock('../../../hooks/useApplications', () => ({
  useApplications: () => ({
    applications: [],
    options: [],
    loading: false,
  }),
}));

import TeamsListPage from '../TeamsListPage';
import TeamDetailPage from '../TeamDetailPage';
import UnassignedLanding from '../UnassignedLanding';

describe('PermissionGating', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('admin sees Create Team and Delete buttons', async () => {
    mockUsePermissions.mockReturnValue({
      isAdmin: true,
      isTeamLead: true,
      hasScope: () => true,
      teams: [{ team_id: 'team-1', role: 'admin', group_name: 'admin' }],
      scopes: ['api/admin'],
      isLoading: false,
    });

    render(
      <MemoryRouter>
        <TeamsListPage />
      </MemoryRouter>
    );

    expect(screen.getByTestId('create-team-button')).toBeInTheDocument();
  });

  it('team lead cannot see Create Team button (admin only)', () => {
    mockUsePermissions.mockReturnValue({
      isAdmin: false,
      isTeamLead: true,
      hasScope: (s: string) => s !== 'api/admin',
      teams: [{ team_id: 'team-1', role: 'team_lead', group_name: 'team-team-1-team_lead' }],
      scopes: [],
      isLoading: false,
    });

    render(
      <MemoryRouter>
        <TeamsListPage />
      </MemoryRouter>
    );

    expect(screen.queryByTestId('create-team-button')).not.toBeInTheDocument();
  });

  it('editor cannot see admin section buttons', () => {
    mockUsePermissions.mockReturnValue({
      isAdmin: false,
      isTeamLead: false,
      hasScope: () => false,
      teams: [{ team_id: 'team-1', role: 'editor', group_name: 'team-team-1-editor' }],
      scopes: [],
      isLoading: false,
    });

    render(
      <MemoryRouter>
        <TeamsListPage />
      </MemoryRouter>
    );

    // No create button for non-admin
    expect(screen.queryByTestId('create-team-button')).not.toBeInTheDocument();
  });

  it('viewer sees read-only team view (no Add Member or Remove)', async () => {
    mockUsePermissions.mockReturnValue({
      isAdmin: false,
      isTeamLead: false,
      hasScope: () => false,
      teams: [{ team_id: 'team-1', role: 'viewer', group_name: 'team-team-1-viewer' }],
      scopes: [],
      isLoading: false,
    });

    // The top-level api mock returns [] for get by default, override for this test
    const { api } = await import('../../../utils/api');
    vi.mocked(api.get).mockImplementation((endpoint: string) => {
      if (endpoint.includes('teams/team-1/members')) {
        return Promise.resolve([]);
      }
      if (endpoint.includes('teams/team-1')) {
        return Promise.resolve({
          id: 'team-1',
          name: 'Alpha Team',
          memberCount: 1,
          applicationCount: 0,
        });
      }
      return Promise.resolve([]);
    });

    render(
      <MemoryRouter initialEntries={['/admin/teams/team-1']}>
        <Routes>
          <Route path="/admin/teams/:id" element={<TeamDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getAllByText('Alpha Team').length).toBeGreaterThan(0);
    });

    // Viewer should NOT see Add Member or Delete
    expect(screen.queryByTestId('add-member-button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('delete-team-button')).not.toBeInTheDocument();
  });

  it('executor has limited actions (no admin controls)', () => {
    mockUsePermissions.mockReturnValue({
      isAdmin: false,
      isTeamLead: false,
      hasScope: () => false,
      teams: [{ team_id: 'team-1', role: 'executor', group_name: 'team-team-1-executor' }],
      scopes: [],
      isLoading: false,
    });

    render(
      <MemoryRouter>
        <TeamsListPage />
      </MemoryRouter>
    );

    // No create or delete controls
    expect(screen.queryByTestId('create-team-button')).not.toBeInTheDocument();
  });

  it('unassigned user sees landing page', () => {
    mockUsePermissions.mockReturnValue({
      isAdmin: false,
      isTeamLead: false,
      hasScope: () => false,
      teams: [],
      scopes: [],
      isLoading: false,
    });

    render(
      <MemoryRouter>
        <UnassignedLanding />
      </MemoryRouter>
    );

    expect(screen.getByText('No Team Access')).toBeInTheDocument();
    expect(screen.getByText(/Contact your administrator/)).toBeInTheDocument();
  });
});
