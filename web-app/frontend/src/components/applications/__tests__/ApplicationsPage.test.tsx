/**
 * ApplicationsPage — the unified applications page (dashboard metrics +
 * management). Covers: card rendering from `dashboard/overview`, suite counts
 * derived from `test-suites`, silent refetch (no spinner swap on reload /
 * window change / refetch failure), cost resilience, permission gating and
 * the delete flow.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import createWrapper from '@cloudscape-design/components/test-utils/dom';
import { CostSummary, DashboardCostsResponse } from '../../../utils/api';

const apiGet = vi.fn();
const apiDelete = vi.fn();
const costsDashboard = vi.fn();
vi.mock('../../../utils/api', () => ({
  api: {
    get: (...a: unknown[]) => apiGet(...a),
    delete: (...a: unknown[]) => apiDelete(...a),
    post: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
  },
  costsApi: {
    dashboard: () => costsDashboard(),
  },
}));

const mockUsePermissions = vi.fn();
vi.mock('../../../auth', async () => {
  const access = await vi.importActual<typeof import('../../../auth/applicationAccess')>('../../../auth/applicationAccess');
  return { ...access, usePermissions: () => mockUsePermissions() };
});

import ApplicationsPage from '../ApplicationsPage';

const perms = (isAdmin: boolean, teams: Array<{ team_id: string; role: string }>) => ({
  isAdmin,
  isTeamLead: teams.some((t) => t.role === 'team_lead'),
  teams: teams.map((t) => ({ ...t, group_name: `team-${t.team_id}-${t.role}` })),
  hasScope: () => true,
  scopes: [],
  isLoading: false,
});

const summary = (window30d: number, changePct: number | null): CostSummary => ({
  as_of: '2026-11-04',
  window_1d: 1, window_1d_trend: 'flat', window_1d_change_pct: 0, window_1d_list: 1,
  window_7d: 7, window_7d_trend: 'flat', window_7d_change_pct: 0, window_7d_list: 7,
  window_30d: window30d,
  window_30d_trend: changePct === null ? null : changePct > 5 ? 'up' : changePct < -5 ? 'down' : 'flat',
  window_30d_change_pct: changePct,
  window_30d_list: window30d,
  by_source_30d: { nova_act: window30d },
  days_available: 61,
  estimated_days: 1,
  updated_at: '2026-11-05T06:02:11Z',
});

const series = {
  dates: ['2026-11-01', '2026-11-02', '2026-11-03'],
  successes: [4, 6, 5],
  failures: [1, 0, 2],
};

const baseApp = {
  base_url: 'https://x.test', description: '', team: 'A', owner_team_id: 'team-a', environments: [],
  created_at: '', updated_at: '', last_execution_id: '', usecase_count: 1,
  pass_rate: 90, total_executions: 10, series,
};

const overview = [
  { ...baseApp, id: 'app-failing', name: 'Failing app', last_execution_status: 'failed', failure_count: 3, last_execution_at: '2026-11-05T05:00:00Z' },
  { ...baseApp, id: 'app-green', name: 'Green app', last_execution_status: 'success', failure_count: 0, last_execution_at: '2026-11-05T06:00:00Z' },
  { ...baseApp, id: 'app-new', name: 'New app', last_execution_status: '', failure_count: 0, last_execution_at: '', series: { dates: [], successes: [], failures: [] } },
];

const suites = {
  suites: [
    { id: 's1', name: 'Suite 1', application_id: 'app-failing' },
    { id: 's2', name: 'Suite 2', application_id: 'app-failing' },
    { id: 's3', name: 'Suite 3', application_id: 'app-green' },
  ],
};

const costs: DashboardCostsResponse = {
  overall: summary(100, 8.5),
  applications: [
    { application_id: 'app-failing', summary: summary(42.1, 12) },
    { application_id: 'app-green', summary: summary(3.5, -20) },
    { application_id: 'app-new', summary: null },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/applications']}>
      <ApplicationsPage />
    </MemoryRouter>,
  );
}

function cardOf(name: string): HTMLElement {
  return screen.getByRole('heading', { name }).closest('[data-testid="application-card"]') as HTMLElement;
}

beforeEach(() => {
  apiGet.mockReset();
  apiDelete.mockReset();
  costsDashboard.mockReset();
  mockUsePermissions.mockReturnValue(perms(true, []));
  apiGet.mockImplementation(async (endpoint: string) => {
    if (endpoint.startsWith('dashboard/overview')) return overview;
    if (endpoint === 'test-suites') return suites;
    if (endpoint.startsWith('teams/')) return { id: 'team-a', name: 'Team A' };
    throw new Error(`unexpected GET ${endpoint}`);
  });
  apiDelete.mockResolvedValue(null);
  costsDashboard.mockResolvedValue(costs);
});

afterEach(() => {
  cleanup();
});

describe('ApplicationsPage cards', () => {
  it('renders one card per application with metrics, cost and footer links', async () => {
    renderPage();
    await screen.findByRole('heading', { name: 'Failing app' });

    const failing = cardOf('Failing app');
    expect(within(failing).getByText('Pass rate')).toBeInTheDocument();
    expect(within(failing).getByText('90%')).toBeInTheDocument();
    expect(within(failing).getByText('10')).toBeInTheDocument();
    expect(within(failing).getByText('3')).toBeInTheDocument();
    expect(within(failing).getByText('$42.10')).toBeInTheDocument();
    expect(within(failing).getByText('Last run: failed', { exact: false })).toBeInTheDocument();

    expect(within(failing).getByRole('link', { name: '1 use case' })).toHaveAttribute('href', '/applications/app-failing?tab=usecases');
    expect(within(failing).getByRole('link', { name: '2 test suites' })).toHaveAttribute('href', '/applications/app-failing?tab=test-suites');
    expect(within(failing).getByRole('link', { name: 'A' })).toHaveAttribute('href', '/admin/teams/team-a');

    const external = within(failing).getByRole('link', { name: /https:\/\/x\.test/ });
    expect(external).toHaveAttribute('href', 'https://x.test');
    expect(external).toHaveAttribute('target', '_blank');
  });

  it('keeps the overview order (failures first) and shows the empty-chart state', async () => {
    renderPage();
    await screen.findByRole('heading', { name: 'Failing app' });
    const names = screen.getAllByTestId('application-card').map(
      (card) => within(card).getByRole('heading').textContent,
    );
    expect(names).toEqual(['Failing app', 'Green app', 'New app']);
    expect(within(cardOf('New app')).getByText('No executions yet')).toBeInTheDocument();
    expect(within(cardOf('New app')).getByTitle('No cost data yet')).toHaveTextContent('—');
  });

  it('fetches overview, suites and costs once each per load', async () => {
    renderPage();
    await screen.findByRole('heading', { name: 'Failing app' });
    expect(apiGet).toHaveBeenCalledTimes(2);
    expect(apiGet).toHaveBeenCalledWith('dashboard/overview?window=7d');
    expect(apiGet).toHaveBeenCalledWith('test-suites');
    expect(costsDashboard).toHaveBeenCalledTimes(1);
  });
});

describe('ApplicationsPage silent refresh', () => {
  it('reload swaps the data in place without a loading spinner', async () => {
    renderPage();
    await screen.findByRole('heading', { name: 'Failing app' });

    const updated = overview.map((a) => (a.id === 'app-failing' ? { ...a, failure_count: 9 } : a));
    apiGet.mockImplementation(async (endpoint: string) => {
      if (endpoint.startsWith('dashboard/overview')) return updated;
      if (endpoint === 'test-suites') return suites;
      throw new Error(`unexpected GET ${endpoint}`);
    });

    fireEvent.click(screen.getByRole('button', { name: 'Reload' }));

    // Old content stays while the refetch is in flight (no spinner swap).
    expect(screen.getByRole('heading', { name: 'Failing app' })).toBeInTheDocument();
    await waitFor(() => expect(within(cardOf('Failing app')).getByText('9')).toBeInTheDocument());
    expect(screen.getByText(/Last updated/)).toBeInTheDocument();
  });

  it('window toggle refetches silently with the new window', async () => {
    renderPage();
    await screen.findByRole('heading', { name: 'Failing app' });

    const control = createWrapper(document.body).findSegmentedControl()!;
    fireEvent.click(control.findSegmentById('30d')!.getElement());

    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('dashboard/overview?window=30d'));
    expect(screen.getByRole('heading', { name: 'Failing app' })).toBeInTheDocument();
  });

  it('keeps the current data when a refetch fails', async () => {
    renderPage();
    await screen.findByRole('heading', { name: 'Failing app' });

    apiGet.mockRejectedValue(new Error('backend exploded'));
    fireEvent.click(screen.getByRole('button', { name: 'Reload' }));

    await screen.findByText('backend exploded');
    expect(screen.getByRole('heading', { name: 'Failing app' })).toBeInTheDocument();
    expect(within(cardOf('Failing app')).getByText('3')).toBeInTheDocument();
  });

  it('shows the error page when the initial load fails', async () => {
    apiGet.mockRejectedValue(new Error('Failed to load applications'));
    renderPage();
    expect(await screen.findByText('Failed to load applications')).toBeInTheDocument();
    expect(screen.queryByTestId('application-card')).not.toBeInTheDocument();
  });

  it('still renders cards when the cost request rejects; cost cells show "—"', async () => {
    costsDashboard.mockRejectedValue(new Error('403 Forbidden'));
    renderPage();
    await screen.findByRole('heading', { name: 'Failing app' });
    expect(screen.getAllByTitle('No cost data yet')).toHaveLength(overview.length);
  });

  it('omits the test-suite link when the suites request fails', async () => {
    apiGet.mockImplementation(async (endpoint: string) => {
      if (endpoint.startsWith('dashboard/overview')) return overview;
      if (endpoint === 'test-suites') throw new Error('no suites');
      throw new Error(`unexpected GET ${endpoint}`);
    });
    renderPage();
    await screen.findByRole('heading', { name: 'Failing app' });
    const failing = cardOf('Failing app');
    expect(within(failing).getByRole('link', { name: '1 use case' })).toBeInTheDocument();
    expect(within(failing).queryByRole('link', { name: /test suite/ })).not.toBeInTheDocument();
  });
});

describe('ApplicationsPage actions', () => {
  it('navigates via the card action dropdown', async () => {
    renderPage();
    await screen.findByRole('heading', { name: 'Failing app' });

    const dropdown = createWrapper(document.body).findButtonDropdown('[data-testid="application-actions-app-failing"]')!;
    act(() => dropdown.openDropdown());
    expect(dropdown.findItemById('edit')).toBeTruthy();
    expect(dropdown.findItemById('add-usecases')).toBeTruthy();
    expect(dropdown.findItemById('add-suites')).toBeTruthy();
    expect(dropdown.findItemById('delete')).toBeTruthy();
    // The three configuration pages ride along as flat items.
    expect(dropdown.findItemById('variables')).toBeTruthy();
    expect(dropdown.findItemById('secrets')).toBeTruthy();
    expect(dropdown.findItemById('datasets')).toBeTruthy();
  });

  it('hides Edit and Delete for a user who cannot manage the application', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'editor' }]));
    renderPage();
    await screen.findByRole('heading', { name: 'Failing app' });

    const dropdown = createWrapper(document.body).findButtonDropdown('[data-testid="application-actions-app-failing"]')!;
    act(() => dropdown.openDropdown());
    expect(dropdown.findItemById('edit')).toBeNull();
    expect(dropdown.findItemById('delete')).toBeNull();
    expect(dropdown.findItemById('add-usecases')).toBeTruthy();
  });

  it('deletes an application after typing the confirmation', async () => {
    renderPage();
    await screen.findByRole('heading', { name: 'Failing app' });

    const dropdown = createWrapper(document.body).findButtonDropdown('[data-testid="application-actions-app-failing"]')!;
    act(() => dropdown.openDropdown());
    act(() => dropdown.findItemById('delete')!.click());

    await screen.findByText('Delete Application');
    const deleteButton = screen.getByRole('button', { name: 'Delete' });
    expect(deleteButton).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText('permanently delete'), { target: { value: 'permanently delete' } });
    fireEvent.click(deleteButton);

    await waitFor(() => expect(apiDelete).toHaveBeenCalledWith('applications/app-failing'));
    await waitFor(() => expect(screen.queryByText('Delete Application')).not.toBeInTheDocument());
    // Refreshes the list after the delete.
    expect(apiGet).toHaveBeenCalledWith('dashboard/overview?window=7d');
  });

  it('shows the team as plain text for non-admins', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'team_lead' }]));
    renderPage();
    await screen.findByRole('heading', { name: 'Failing app' });
    const failing = cardOf('Failing app');
    expect(within(failing).queryByRole('link', { name: 'A' })).not.toBeInTheDocument();
    expect(within(failing).getByText(/team A/)).toBeInTheDocument();
  });

  it('shows the empty state with a create action', async () => {
    apiGet.mockImplementation(async (endpoint: string) => {
      if (endpoint.startsWith('dashboard/overview')) return [];
      if (endpoint === 'test-suites') return { suites: [] };
      throw new Error(`unexpected GET ${endpoint}`);
    });
    renderPage();
    await screen.findByText('No applications yet');
    expect(screen.getByRole('button', { name: 'Create your first application' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create application' })).toBeInTheDocument();
  });
});
