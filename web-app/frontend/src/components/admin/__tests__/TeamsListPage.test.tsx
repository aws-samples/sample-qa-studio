import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import TeamsListPage from '../TeamsListPage';

// Mock hooks
const mockUseTeams = vi.fn();
vi.mock('../../../hooks/useTeams', () => ({
  useTeams: () => mockUseTeams(),
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

function renderPage() {
  return render(
    <MemoryRouter>
      <TeamsListPage />
    </MemoryRouter>
  );
}

describe('TeamsListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUsePermissions.mockReturnValue({
      isAdmin: true,
      isTeamLead: false,
      hasScope: () => true,
      teams: [],
      scopes: [],
      isLoading: false,
    });
  });

  it('renders teams table with data', async () => {
    mockUseTeams.mockReturnValue({
      teams: [
        { id: 'team-1', name: 'Alpha Team', memberCount: 3, applicationCount: 2 },
        { id: 'team-2', name: 'Beta Team', memberCount: 5, applicationCount: 1 },
      ],
      loading: false,
      error: null,
      fetchTeams: vi.fn(),
      createTeam: vi.fn(),
      deleteTeam: vi.fn(),
    });

    renderPage();

    expect(screen.getByText('Alpha Team')).toBeInTheDocument();
    expect(screen.getByText('Beta Team')).toBeInTheDocument();
    expect(screen.getByText('(2)')).toBeInTheDocument();
  });

  it('filters teams by search text', async () => {
    mockUseTeams.mockReturnValue({
      teams: [
        { id: 'team-1', name: 'Alpha Team', memberCount: 3, applicationCount: 2 },
        { id: 'team-2', name: 'Beta Team', memberCount: 5, applicationCount: 1 },
      ],
      loading: false,
      error: null,
      fetchTeams: vi.fn(),
      createTeam: vi.fn(),
      deleteTeam: vi.fn(),
    });

    renderPage();

    const filterInput = screen.getByPlaceholderText('Find teams');
    fireEvent.change(filterInput, { target: { value: 'Alpha' } });

    await waitFor(() => {
      expect(screen.getByText('Alpha Team')).toBeInTheDocument();
      expect(screen.queryByText('Beta Team')).not.toBeInTheDocument();
    });
  });

  it('opens create team modal when button clicked', async () => {
    mockUseTeams.mockReturnValue({
      teams: [],
      loading: false,
      error: null,
      fetchTeams: vi.fn(),
      createTeam: vi.fn(),
      deleteTeam: vi.fn(),
    });

    renderPage();

    const createButton = screen.getByTestId('create-team-button');
    fireEvent.click(createButton);

    await waitFor(() => {
      // The modal renders a "Team name" label and submit/cancel buttons
      expect(screen.getByText('Team name')).toBeInTheDocument();
      expect(screen.getByTestId('create-team-submit')).toBeInTheDocument();
    });
  });

  it('shows empty state with create CTA', () => {
    mockUseTeams.mockReturnValue({
      teams: [],
      loading: false,
      error: null,
      fetchTeams: vi.fn(),
      createTeam: vi.fn(),
      deleteTeam: vi.fn(),
    });

    renderPage();

    expect(screen.getByText('No teams')).toBeInTheDocument();
    expect(screen.getByTestId('empty-create-team')).toBeInTheDocument();
  });

  it('shows loading state', () => {
    mockUseTeams.mockReturnValue({
      teams: [],
      loading: true,
      error: null,
      fetchTeams: vi.fn(),
      createTeam: vi.fn(),
      deleteTeam: vi.fn(),
    });

    renderPage();

    expect(screen.getByText('Loading teams...')).toBeInTheDocument();
  });
});
