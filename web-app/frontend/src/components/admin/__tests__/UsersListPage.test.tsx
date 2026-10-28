import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import UsersListPage from '../UsersListPage';

const mockUseUsers = vi.fn();
vi.mock('../../../hooks/useUsers', () => ({
  useUsers: () => mockUseUsers(),
}));

vi.mock('../../../hooks/useTeams', () => ({
  useTeams: () => ({
    teams: [{ id: 'team-1', name: 'Alpha', memberCount: 2, applicationCount: 1 }],
    loading: false,
    error: null,
    fetchTeams: vi.fn(),
    createTeam: vi.fn(),
    deleteTeam: vi.fn(),
  }),
}));

vi.mock('../../../auth', () => ({
  usePermissions: () => ({
    isAdmin: true,
    isTeamLead: false,
    hasScope: () => true,
    teams: [],
    scopes: [],
    isLoading: false,
  }),
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <UsersListPage />
    </MemoryRouter>
  );
}

describe('UsersListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders users table with data', () => {
    mockUseUsers.mockReturnValue({
      users: [
        { userId: 'u-1', email: 'alice@example.com', teams: [{ teamId: 'team-1', name: 'Alpha', role: 'editor' }] },
        { userId: 'u-2', email: 'bob@example.com', teams: [] },
      ],
      loading: false,
      error: null,
      fetchUsers: vi.fn(),
      createUser: vi.fn(),
      updateUser: vi.fn(),
      deleteUser: vi.fn(),
    });

    renderPage();

    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    expect(screen.getByText('bob@example.com')).toBeInTheDocument();
  });

  it('opens create user modal', () => {
    mockUseUsers.mockReturnValue({
      users: [],
      loading: false,
      error: null,
      fetchUsers: vi.fn(),
      createUser: vi.fn(),
      updateUser: vi.fn(),
      deleteUser: vi.fn(),
    });

    renderPage();

    fireEvent.click(screen.getByTestId('create-user-button'));

    // Modal opened — check for the submit and cancel buttons
    expect(screen.getByTestId('create-user-submit')).toBeInTheDocument();
    expect(screen.getByTestId('create-user-cancel')).toBeInTheDocument();
  });

  it('shows unassigned indicator for users without teams', () => {
    mockUseUsers.mockReturnValue({
      users: [
        { userId: 'u-2', email: 'bob@example.com', teams: [] },
      ],
      loading: false,
      error: null,
      fetchUsers: vi.fn(),
      createUser: vi.fn(),
      updateUser: vi.fn(),
      deleteUser: vi.fn(),
    });

    renderPage();

    expect(screen.getByText('Unassigned')).toBeInTheDocument();
  });

  it('filters users by email', async () => {
    mockUseUsers.mockReturnValue({
      users: [
        { userId: 'u-1', email: 'alice@example.com', teams: [] },
        { userId: 'u-2', email: 'bob@example.com', teams: [] },
      ],
      loading: false,
      error: null,
      fetchUsers: vi.fn(),
      createUser: vi.fn(),
      updateUser: vi.fn(),
      deleteUser: vi.fn(),
    });

    renderPage();

    const filterInput = screen.getByPlaceholderText('Find users by email');
    fireEvent.change(filterInput, { target: { value: 'alice' } });

    await waitFor(() => {
      expect(screen.getByText('alice@example.com')).toBeInTheDocument();
      expect(screen.queryByText('bob@example.com')).not.toBeInTheDocument();
    });
  });
});
