/**
 * Application detail page: the Actions dropdown carries Edit / Assign to team
 * (permission-gated) and the Configuration group that links to the
 * Variables / Secrets / Datasets pages; the Usecases tab dropdown offers
 * Delete selected (real `useBatchDelete`, only `api.delete` mocked); the Cost
 * tab hosts the cost card with the use-case table (hidden on 403/404).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import createWrapper from '@cloudscape-design/components/test-utils/dom';

const mockUsePermissions = vi.fn();
vi.mock('../../../auth', async () => {
  const access = await vi.importActual<typeof import('../../../auth/applicationAccess')>('../../../auth/applicationAccess');
  return { ...access, usePermissions: () => mockUsePermissions() };
});

const apiGet = vi.fn();
const apiDelete = vi.fn();
const costsApplication = vi.fn();
vi.mock('../../../utils/api', () => ({
  api: {
    get: (...a: unknown[]) => apiGet(...a),
    post: vi.fn().mockResolvedValue({}),
    delete: (...a: unknown[]) => apiDelete(...a),
  },
  costsApi: {
    application: (...a: unknown[]) => costsApplication(...a),
  },
}));

vi.mock('../../../hooks/useBatchExecute', () => ({
  useBatchExecute: () => ({ executeBatch: vi.fn().mockResolvedValue([]), executing: false }),
}));

import ApplicationDetailView from '../ApplicationDetailView';

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

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderDetail(initialEntry = '/applications/app-1') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/applications/:id" element={<ApplicationDetailView />} />
        <Route path="*" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function openActions() {
  await screen.findByRole('heading', { name: 'Shop' });
  const dropdown = createWrapper(document.body).findButtonDropdown('[data-testid="application-actions"]')!;
  act(() => dropdown.openDropdown());
  return dropdown;
}

beforeEach(() => {
  apiGet.mockReset();
  apiDelete.mockReset();
  costsApplication.mockReset();
  mockUsePermissions.mockReset();
  costsApplication.mockReturnValue(new Promise(() => undefined));
  apiGet.mockImplementation(async (endpoint: string) => {
    if (endpoint === 'applications/app-1') return app;
    if (endpoint.startsWith('dashboard/overview')) return [];
    if (endpoint === 'usecases') return { usecases: [] };
    if (endpoint === 'test-suites') return { suites: [] };
    throw new Error(`unexpected GET ${endpoint}`);
  });
});
afterEach(() => {
  cleanup();
});

describe('ApplicationDetailView actions', () => {
  it('offers the Configuration group to a viewer and hides Edit / Assign to team', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'editor' }]));
    renderDetail();
    const dropdown = await openActions();
    expect(dropdown.findOpenDropdown()!.getElement().textContent).toContain('Configuration');
    expect(dropdown.findItemById('variables')).not.toBeNull();
    expect(dropdown.findItemById('secrets')).not.toBeNull();
    expect(dropdown.findItemById('datasets')).not.toBeNull();
    expect(dropdown.findItemById('edit')).toBeNull();
    expect(dropdown.findItemById('reassign')).toBeNull();
  });

  it('offers Edit to the owner team lead but not Assign to team', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'team_lead' }]));
    renderDetail();
    const dropdown = await openActions();
    expect(dropdown.findItemById('edit')).not.toBeNull();
    expect(dropdown.findItemById('reassign')).toBeNull();
  });

  it('offers Edit and Assign to team to an admin', async () => {
    mockUsePermissions.mockReturnValue(perms(true, []));
    renderDetail();
    const dropdown = await openActions();
    expect(dropdown.findItemById('edit')).not.toBeNull();
    expect(dropdown.findItemById('reassign')).not.toBeNull();
  });

  it.each([
    ['variables', '/applications/app-1/variables'],
    ['secrets', '/applications/app-1/secrets'],
    ['datasets', '/applications/app-1/datasets'],
    ['edit', '/applications/app-1/edit'],
  ])('navigates to %s', async (itemId, expectedPath) => {
    mockUsePermissions.mockReturnValue(perms(true, []));
    renderDetail();
    const dropdown = await openActions();
    act(() => dropdown.findItemById(itemId)!.click());
    expect((await screen.findByTestId('location')).textContent).toBe(expectedPath);
  });

  it('opens the reassign modal from Assign to team', async () => {
    mockUsePermissions.mockReturnValue(perms(true, []));
    apiGet.mockImplementation(async (endpoint: string) => {
      if (endpoint === 'applications/app-1') return app;
      if (endpoint.startsWith('dashboard/overview')) return [];
      if (endpoint === 'usecases') return { usecases: [] };
      if (endpoint === 'test-suites') return { suites: [] };
      if (endpoint === 'teams') return [];
      throw new Error(`unexpected GET ${endpoint}`);
    });
    renderDetail();
    const dropdown = await openActions();
    act(() => dropdown.findItemById('reassign')!.click());
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });
});

const usecase = (id: string, name: string, applicationId = 'app-1') => ({
  id, name, application_id: applicationId, active: true,
});

/** Serve `GET usecases` from a mutable list; a successful `DELETE usecase/{id}` removes the entry. */
function withUsecases(initial: ReturnType<typeof usecase>[], failIds: string[] = []) {
  let stored = [...initial];
  apiGet.mockImplementation(async (endpoint: string) => {
    if (endpoint === 'applications/app-1') return app;
    if (endpoint.startsWith('dashboard/overview')) return [];
    if (endpoint === 'usecases') return { usecases: stored };
    if (endpoint === 'test-suites') return { suites: [] };
    throw new Error(`unexpected GET ${endpoint}`);
  });
  apiDelete.mockImplementation(async (path: string) => {
    const id = path.replace('usecase/', '');
    if (failIds.includes(id)) throw new Error('HTTP 403');
    stored = stored.filter((u) => u.id !== id);
  });
}

const usecasesGets = () => apiGet.mock.calls.filter(([endpoint]) => endpoint === 'usecases').length;
const usecaseActions = () => createWrapper(document.body).findButtonDropdown('[data-testid="usecase-actions"]')!;
const usecasesTabLabel = () =>
  createWrapper(document.body).findTabs()!.findTabLinkById('usecases')!.getElement().textContent;

async function renderUsecasesTab() {
  renderDetail();
  await screen.findByRole('heading', { name: 'Shop' });
}

/** Tick the row's checkbox (1-based). The page re-renders after a reload, so look the table up every time. */
function selectRow(index: number) {
  const table = createWrapper(document.body).findTable()!;
  fireEvent.click(table.findRowSelectionArea(index)!.find('input')!.getElement());
}

function openUsecaseActions() {
  const dropdown = usecaseActions();
  act(() => dropdown.openDropdown());
  return dropdown;
}

function clickDeleteSelected() {
  const dropdown = openUsecaseActions();
  act(() => dropdown.findItemById('delete-selected')!.click());
}

function confirmDelete() {
  fireEvent.change(screen.getByLabelText('Confirmation text'), { target: { value: 'permanently delete' } });
  const confirm = screen.getAllByRole('button', { name: 'Delete' }).find((b) => b.closest('[role="dialog"]'))!;
  fireEvent.click(confirm);
}

describe('ApplicationDetailView delete selected use cases', () => {
  const editor = () => perms(false, [{ team_id: 'team-a', role: 'editor' }]);
  const login = usecase('uc-1', 'Login');
  const checkout = usecase('uc-2', 'Checkout');
  const elsewhere = usecase('uc-9', 'Elsewhere', 'app-2');

  it('offers Delete selected (0) after Remove selected, disabled while nothing is selected', async () => {
    mockUsePermissions.mockReturnValue(editor());
    withUsecases([login, checkout]);
    await renderUsecasesTab();
    const dropdown = openUsecaseActions();
    expect(dropdown.findItems().map((i) => i.getElement().getAttribute('data-testid'))).toEqual([
      'remove-selected', 'delete-selected', 'add-usecases',
    ]);
    const item = dropdown.findItemById('delete-selected')!;
    expect(item.getElement().textContent).toBe('Delete selected (0)');
    expect(item.find('[role="menuitem"]')!.getElement()).toHaveAttribute('aria-disabled', 'true');
  });

  it('offers Delete selected to a viewer of another team (the server checks permission)', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-b', role: 'viewer' }]));
    withUsecases([login]);
    await renderUsecasesTab();
    selectRow(1);
    const item = openUsecaseActions().findItemById('delete-selected')!;
    expect(item.getElement().textContent).toBe('Delete selected (1)');
    expect(item.find('[role="menuitem"]')!.getElement()).not.toHaveAttribute('aria-disabled', 'true');
  });

  it('does not render the confirmation dialog until Delete selected is picked', async () => {
    mockUsePermissions.mockReturnValue(editor());
    withUsecases([login]);
    await renderUsecasesTab();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
  });

  it('shows the selection count in the item and in the dialog', async () => {
    mockUsePermissions.mockReturnValue(editor());
    withUsecases([login, checkout]);
    await renderUsecasesTab();
    selectRow(1);
    selectRow(2);
    expect(openUsecaseActions().findItemById('delete-selected')!.getElement().textContent).toBe('Delete selected (2)');
    act(() => usecaseActions().findItemById('delete-selected')!.click());

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Delete Use Cases')).toBeInTheDocument();
    expect(
      screen.getByText(
        'You are about to permanently delete 2 use cases. This will remove all associated data including steps, executions, and configurations.',
      ),
    ).toBeInTheDocument();
  });

  it('deletes every selected use case, reports success and reloads the use cases', async () => {
    mockUsePermissions.mockReturnValue(editor());
    withUsecases([login, checkout, elsewhere]);
    await renderUsecasesTab();
    expect(usecasesTabLabel()).toBe('Usecases (2)');
    expect(usecasesGets()).toBe(1);

    selectRow(1);
    selectRow(2);
    clickDeleteSelected();
    await screen.findByRole('dialog');
    confirmDelete();

    expect((await screen.findAllByText('Successfully deleted 2 use case(s)')).length).toBeGreaterThan(0);
    expect(apiDelete).toHaveBeenCalledTimes(2);
    expect(apiDelete).toHaveBeenCalledWith('usecase/uc-1');
    expect(apiDelete).toHaveBeenCalledWith('usecase/uc-2');
    await vi.waitFor(() => expect(usecasesTabLabel()).toBe('Usecases (0)'));
    expect(usecasesGets()).toBe(2);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(openUsecaseActions().findItemById('delete-selected')!.getElement().textContent).toBe('Delete selected (0)');
  });

  it('shows the failed use case in an error flash and keeps the page when a delete fails', async () => {
    mockUsePermissions.mockReturnValue(editor());
    withUsecases([login, checkout], ['uc-2']);
    await renderUsecasesTab();

    selectRow(1);
    selectRow(2);
    clickDeleteSelected();
    await screen.findByRole('dialog');
    confirmDelete();

    expect((await screen.findAllByText('Failed to delete 1 use case(s): Checkout')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Successfully deleted 1 use case(s)').length).toBeGreaterThan(0);
    await vi.waitFor(() => expect(usecasesTabLabel()).toBe('Usecases (1)'));
    // No page-wide error Alert: the header and the table are still there.
    expect(screen.getByRole('heading', { name: 'Shop' })).toBeInTheDocument();
    expect(screen.queryByText('Error')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Checkout' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Login' })).not.toBeInTheDocument();
  });

  it('deletes nothing and keeps the selection on Cancel', async () => {
    mockUsePermissions.mockReturnValue(editor());
    withUsecases([login, checkout]);
    await renderUsecasesTab();

    selectRow(1);
    clickDeleteSelected();
    await screen.findByRole('dialog');
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    await vi.waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(apiDelete).not.toHaveBeenCalled();
    expect(usecasesGets()).toBe(1);
    expect(openUsecaseActions().findItemById('delete-selected')!.getElement().textContent).toBe('Delete selected (1)');
  });
});

const costSummary = {
  as_of: '2026-11-04',
  window_1d: 1.42, window_1d_trend: 'up', window_1d_change_pct: 29.1, window_1d_list: 1.5,
  window_7d: 9.8, window_7d_trend: 'down', window_7d_change_pct: -10.1, window_7d_list: 10.2,
  window_30d: 42.1, window_30d_trend: null, window_30d_change_pct: null, window_30d_list: 44.0,
  by_source_30d: { nova_act: 42.1 },
  days_available: 31,
  estimated_days: 0,
  updated_at: '2026-11-05T06:02:11Z',
};

function httpError(status: number) {
  const err = new Error(`HTTP ${status}`);
  (err as Error & { status: number }).status = status;
  return err;
}

describe('ApplicationDetailView cost tab', () => {
  it('offers a Cost tab next to Metrics and does not request costs until it is opened', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'editor' }]));
    renderDetail();
    await screen.findByRole('heading', { name: 'Shop' });
    const tabs = createWrapper(document.body).findTabs()!;
    expect(tabs.findTabLinkById('costs')!.getElement().textContent).toBe('Cost');
    expect(costsApplication).not.toHaveBeenCalled();
  });

  it('renders the cost card with the use-case table on the Cost tab for a viewer', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'editor' }]));
    costsApplication.mockResolvedValue({
      summary: costSummary,
      days: [],
      usecases: [{ usecase_id: 'uc-1', name: 'Checkout', summary: costSummary }],
    });
    renderDetail('/applications/app-1?tab=costs');
    // Card figure + the Checkout row's 30d cell.
    await vi.waitFor(() => expect(screen.getAllByText('$42.10')).toHaveLength(2));
    expect(screen.getByText('Source: Nova Act · Cost Explorer as of 2026-11-04')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Checkout' })).toBeInTheDocument();
    expect(costsApplication).toHaveBeenCalledTimes(1);
    expect(costsApplication).toHaveBeenCalledWith('app-1');
  });

  it('shows no cost card when the API answers 403', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'editor' }]));
    costsApplication.mockRejectedValue(httpError(403));
    renderDetail('/applications/app-1?tab=costs');
    await screen.findByRole('heading', { name: 'Shop' });
    await vi.waitFor(() => expect(costsApplication).toHaveBeenCalled());
    await vi.waitFor(() => expect(screen.queryByRole('heading', { name: 'Cost' })).not.toBeInTheDocument());
    expect(screen.queryByText(/No cost data yet/)).not.toBeInTheDocument();
  });

  it('shows an error alert inside the card when the API fails', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'editor' }]));
    costsApplication.mockRejectedValue(httpError(500));
    renderDetail('/applications/app-1?tab=costs');
    expect(await screen.findByText('HTTP 500')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Cost' })).toBeInTheDocument();
  });
});
