/**
 * Shell shared by the application Variables / Secrets / Datasets pages:
 * loads the application, renders breadcrumbs + header, gates writes via
 * canManageApplication and surfaces load errors.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Button from '@cloudscape-design/components/button';
import createWrapper from '@cloudscape-design/components/test-utils/dom';

const mockUsePermissions = vi.fn();
vi.mock('../../../auth', async () => {
  const access = await vi.importActual<typeof import('../../../auth/applicationAccess')>('../../../auth/applicationAccess');
  return { ...access, usePermissions: () => mockUsePermissions() };
});

const apiGet = vi.fn();
vi.mock('../../../utils/api', () => ({
  api: { get: (...a: unknown[]) => apiGet(...a) },
}));

import ApplicationConfigPage from '../ApplicationConfigPage';
import ApplicationVariablesPage from '../ApplicationVariablesPage';
import ApplicationSecretsPage from '../ApplicationSecretsPage';
import ApplicationDatasetsPage from '../ApplicationDatasetsPage';

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

function renderAt(path: string, pattern: string, element: React.ReactElement) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={pattern} element={element} />
      </Routes>
    </MemoryRouter>,
  );
}

const breadcrumbTexts = () =>
  createWrapper(document.body).findBreadcrumbGroup()!.findBreadcrumbLinks().map((l) => l.getElement().textContent?.trim());

beforeEach(() => {
  apiGet.mockReset();
  mockUsePermissions.mockReset();
  mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'team_lead' }]));
});
afterEach(() => {
  cleanup();
});

describe('ApplicationConfigPage', () => {
  it('shows a spinner while loading, then breadcrumbs Applications → app → page and the header', async () => {
    let resolve!: (v: unknown) => void;
    apiGet.mockReturnValue(new Promise((r) => { resolve = r; }));
    renderAt('/applications/app-1/variables', '/applications/:id/variables',
      <ApplicationConfigPage title="Variables" description="Shared values">{() => <div>body</div>}</ApplicationConfigPage>);

    expect(createWrapper(document.body).findSpinner()).not.toBeNull();
    expect(screen.queryByText('body')).toBeNull();

    resolve(app);
    expect(await screen.findByRole('heading', { name: 'Variables' })).toBeInTheDocument();
    expect(apiGet).toHaveBeenCalledWith('applications/app-1');
    expect(screen.getByText('Shared values')).toBeInTheDocument();
    expect(screen.getByText('body')).toBeInTheDocument();

    expect(breadcrumbTexts()).toEqual(['Applications', 'Shop', 'Variables']);
    expect(screen.getByRole('link', { name: 'Shop' })).toHaveAttribute('href', '/applications/app-1');
  });

  it('passes readOnly=false and the application to the owner team lead', async () => {
    apiGet.mockResolvedValue(app);
    const body = vi.fn(() => <div>body</div>);
    renderAt('/applications/app-1/variables', '/applications/:id/variables',
      <ApplicationConfigPage title="Variables" description="d">{body}</ApplicationConfigPage>);
    await screen.findByText('body');
    expect(body).toHaveBeenCalledWith({ application: app, readOnly: false });
    expect(screen.queryByText(/read-only/)).toBeNull();
  });

  it('passes readOnly=true to an editor and explains it; write controls stay disabled', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'editor' }]));
    apiGet.mockResolvedValue(app);
    renderAt('/applications/app-1/variables', '/applications/:id/variables',
      <ApplicationConfigPage title="Variables" description="d">
        {({ readOnly }) => (
          <Button disabled={readOnly} disabledReason="Read-only">Add variable</Button>
        )}
      </ApplicationConfigPage>);
    const button = await screen.findByRole('button', { name: 'Add variable' });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByText(/read-only/)).toBeInTheDocument();
  });

  it('passes readOnly=true to a team lead of another team', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-b', role: 'team_lead' }]));
    apiGet.mockResolvedValue(app);
    const body = vi.fn(() => <div>body</div>);
    renderAt('/applications/app-1/variables', '/applications/:id/variables',
      <ApplicationConfigPage title="Variables" description="d">{body}</ApplicationConfigPage>);
    await screen.findByText('body');
    expect(body).toHaveBeenCalledWith({ application: app, readOnly: true });
  });

  it('passes readOnly=false to an admin', async () => {
    mockUsePermissions.mockReturnValue(perms(true, []));
    apiGet.mockResolvedValue(app);
    const body = vi.fn(() => <div>body</div>);
    renderAt('/applications/app-1/variables', '/applications/:id/variables',
      <ApplicationConfigPage title="Variables" description="d">{body}</ApplicationConfigPage>);
    await screen.findByText('body');
    expect(body).toHaveBeenCalledWith({ application: app, readOnly: false });
  });

  it('shows an error alert and no body when the application fails to load', async () => {
    apiGet.mockRejectedValue(new Error('Forbidden'));
    const body = vi.fn(() => <div>body</div>);
    renderAt('/applications/app-1/variables', '/applications/:id/variables',
      <ApplicationConfigPage title="Variables" description="d">{body}</ApplicationConfigPage>);
    expect(await screen.findByText('Forbidden')).toBeInTheDocument();
    expect(body).not.toHaveBeenCalled();
    expect(screen.getByRole('heading', { name: 'Variables' })).toBeInTheDocument();
    expect(breadcrumbTexts()).toContain('Applications');
  });

  it('shows an error when the route has no application id', async () => {
    renderAt('/x', '/x', <ApplicationConfigPage title="Variables" description="d">{() => <div>body</div>}</ApplicationConfigPage>);
    expect(await screen.findByText('Application ID not found')).toBeInTheDocument();
    expect(apiGet).not.toHaveBeenCalled();
  });
});

describe.each([
  ['Variables', ApplicationVariablesPage, '/applications/:id/variables'],
  ['Secrets', ApplicationSecretsPage, '/applications/:id/secrets'],
  ['Datasets', ApplicationDatasetsPage, '/applications/:id/datasets'],
] as const)('%s page', (title, Page, pattern) => {
  it('renders breadcrumbs with the application name and its header', async () => {
    apiGet.mockResolvedValue(app);
    renderAt(pattern.replace(':id', 'app-1'), pattern, <Page />);
    expect(await screen.findByRole('heading', { name: title })).toBeInTheDocument();
    expect(apiGet).toHaveBeenCalledWith('applications/app-1');
    expect(breadcrumbTexts()).toEqual(['Applications', 'Shop', title]);
  });

  it('renders no write controls for a read-only user', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'editor' }]));
    apiGet.mockResolvedValue(app);
    renderAt(pattern.replace(':id', 'app-1'), pattern, <Page />);
    await screen.findByRole('heading', { name: title });
    expect(screen.getByText(/read-only/)).toBeInTheDocument();
    // Breadcrumbs collapse into a dropdown button in jsdom (zero width); that is navigation, not a write control.
    const enabledButtons = screen.queryAllByRole('button')
      .filter((b) => !b.closest('nav'))
      .filter((b) => b.getAttribute('aria-disabled') !== 'true' && !(b as HTMLButtonElement).disabled);
    expect(enabledButtons).toEqual([]);
  });
});
