import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

const mockUsePermissions = vi.fn();
vi.mock('../../auth', async () => {
  const access = await vi.importActual<typeof import('../../auth/applicationAccess')>('../../auth/applicationAccess');
  return { ...access, usePermissions: () => mockUsePermissions() };
});

const mockGet = vi.fn();
const mockPost = vi.fn();
vi.mock('../../utils/api', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(null),
  },
}));

import ApplicationSettings from '../ApplicationSettings';
import EditApplication from '../EditApplication';
import { CreateApplicationModal } from '../dashboard/CreateApplicationModal';

const perms = (isAdmin: boolean, teams: Array<{ team_id: string; role: string }>) => ({
  isAdmin,
  isTeamLead: teams.some((t) => t.role === 'team_lead'),
  teams: teams.map((t) => ({ ...t, group_name: `team-${t.team_id}-${t.role}` })),
  hasScope: () => true,
  scopes: [],
  isLoading: false,
});

describe('Application gating (H-3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockImplementation(async (endpoint: string) => {
      if (endpoint === 'applications') return [];
      if (endpoint.startsWith('applications/')) {
        return { id: 'app-1', name: 'App', base_url: 'https://a', description: '', team: 'A',
          owner_team_id: 'team-a', environments: [] };
      }
      if (endpoint.startsWith('teams/')) {
        const id = decodeURIComponent(endpoint.split('/')[1]);
        return { id, name: `Team ${id}` };
      }
      return [];
    });
  });

  it('hides Create application for an editor', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'editor' }]));
    render(<MemoryRouter><ApplicationSettings /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('No applications yet')).toBeTruthy());
    expect(screen.queryByText('Create application')).toBeNull();
    expect(screen.queryByText('Create your first application')).toBeNull();
  });

  it('shows Create application for a team lead and an admin', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'team_lead' }]));
    const { unmount } = render(<MemoryRouter><ApplicationSettings /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('Create application')).toBeTruthy());
    unmount();
    mockUsePermissions.mockReturnValue(perms(true, []));
    render(<MemoryRouter><ApplicationSettings /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('Create application')).toBeTruthy());
  });

  it('create modal offers only led teams and requires a team', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [
      { team_id: 'team-a', role: 'team_lead' },
      { team_id: 'team-b', role: 'editor' },
    ]));
    render(<CreateApplicationModal visible onDismiss={vi.fn()} onSuccess={vi.fn()} />);
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('teams/team-a'));
    expect(mockGet).not.toHaveBeenCalledWith('teams/team-b');
  });

  it('create modal sends teamId of the selected team', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'team_lead' }]));
    mockPost.mockResolvedValue({});
    render(<CreateApplicationModal visible onDismiss={vi.fn()} onSuccess={vi.fn()} />);
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('teams/team-a'));
    const inputs = document.body.querySelectorAll('input');
    fireEvent.change(inputs[0], { target: { value: 'My App' } });
    fireEvent.change(inputs[1], { target: { value: 'https://app.example.com' } });
    // The single led team is preselected once its name is loaded.
    await waitFor(() => expect(screen.getByText('Team team-a')).toBeTruthy());
    fireEvent.click(screen.getByText('Create'));
    await waitFor(() => expect(mockPost).toHaveBeenCalled());
    expect(mockPost.mock.calls[0][0]).toBe('applications');
    expect(mockPost.mock.calls[0][1].teamId).toBe('team-a');
  });

  it('create modal blocks submit without a team', async () => {
    mockUsePermissions.mockReturnValue(perms(true, []));
    render(<CreateApplicationModal visible onDismiss={vi.fn()} onSuccess={vi.fn()} />);
    const inputs = document.body.querySelectorAll('input');
    fireEvent.change(inputs[0], { target: { value: 'My App' } });
    fireEvent.change(inputs[1], { target: { value: 'https://app.example.com' } });
    fireEvent.click(screen.getByText('Create'));
    await waitFor(() => expect(screen.getByText('Team is required')).toBeTruthy());
    expect(mockPost).not.toHaveBeenCalled();
  });

  const renderEdit = () => render(
    <MemoryRouter initialEntries={['/applications/app-1/edit']}>
      <Routes><Route path="/applications/:id/edit" element={<EditApplication />} /></Routes>
    </MemoryRouter>,
  );

  it('edit page hides Save and Delete for an owner-team editor', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'editor' }]));
    renderEdit();
    await waitFor(() => expect(screen.getByText(/Only a team lead of the owning team/)).toBeTruthy());
    expect(screen.queryByText('Save')).toBeNull();
    expect(screen.queryByText('Delete this application')).toBeNull();
  });

  it('edit page shows Save and Delete for the owner team lead', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'team_lead' }]));
    renderEdit();
    await waitFor(() => expect(screen.getByText('Save')).toBeTruthy());
    expect(screen.getByText('Delete this application')).toBeTruthy();
    expect(screen.queryByText(/Only a team lead of the owning team/)).toBeNull();
  });

  it('edit page hides actions for a team lead of another team', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-b', role: 'team_lead' }]));
    renderEdit();
    await waitFor(() => expect(screen.getByText(/Only a team lead of the owning team/)).toBeTruthy());
    expect(screen.queryByText('Save')).toBeNull();
  });
});
