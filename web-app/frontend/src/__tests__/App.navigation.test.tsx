/**
 * Side navigation of the app shell: the Applications group lists Variables /
 * Secrets / Datasets only while an application route is open, and the
 * current child is highlighted.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import createWrapper from '@cloudscape-design/components/test-utils/dom';

vi.mock('aws-amplify', () => ({ Amplify: { configure: vi.fn() } }));
vi.mock('@aws-amplify/ui-react', () => ({
  Authenticator: ({ children }: { children: (p: { signOut: () => void; user: unknown }) => React.ReactNode }) =>
    <>{children({ signOut: vi.fn(), user: { username: 'tester' } })}</>,
}));
vi.mock('@aws-amplify/ui-react/styles.css', () => ({}));
vi.mock('../amplifyconfiguration.json', () => ({ default: {} }));

const permissions = {
  isAdmin: false,
  isTeamLead: false,
  teams: [{ team_id: 'team-a', role: 'editor', group_name: 'team-a-editor' }],
  hasScope: () => false,
  scopes: [],
  isLoading: false,
};
vi.mock('../auth', async () => {
  const access = await vi.importActual<typeof import('../auth/applicationAccess')>('../auth/applicationAccess');
  return {
    ...access,
    PermissionsProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    usePermissions: () => permissions,
  };
});

const apiGet = vi.fn();
vi.mock('../utils/api', () => ({
  api: {
    get: (...a: unknown[]) => apiGet(...a),
    post: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(null),
  },
}));

import App from '../App';

const app = { id: 'app-1', name: 'Shop', base_url: 'https://shop.test', description: '', team: 'A',
  owner_team_id: 'team-a', environments: [] };

function renderAt(path: string) {
  window.history.pushState({}, '', path);
  return render(<App />);
}

function applicationsGroup() {
  const nav = createWrapper(screen.getByTestId('nav-sidebar')).findSideNavigation()!;
  const group = nav.findItemByIndex(1)!.findExpandableLinkGroup();
  expect(group, 'Applications must be an expandable link group').not.toBeNull();
  return group!;
}

const childLinkTexts = () =>
  within(applicationsGroup().findContent().getElement()).queryAllByRole('link').map((a) => a.textContent?.trim());

beforeEach(() => {
  apiGet.mockReset();
  apiGet.mockImplementation(async (endpoint: string) => {
    if (endpoint === 'applications/app-1') return app;
    if (endpoint === 'applications') return [];
    if (endpoint.startsWith('dashboard/overview')) return [];
    if (endpoint === 'usecases') return { usecases: [] };
    if (endpoint === 'test-suites') return { suites: [] };
    return [];
  });
});
afterEach(() => {
  cleanup();
  window.history.pushState({}, '', '/');
});

describe('App navigation — Applications group', () => {
  it('shows only the group link outside application routes', async () => {
    renderAt('/about');
    await screen.findByTestId('nav-sidebar');
    expect(applicationsGroup().findHeader().getElement().querySelector('a')).toHaveAttribute('href', '/applications');
    expect(childLinkTexts()).toEqual([]);
  });

  it('shows no children on the applications list page', async () => {
    renderAt('/applications');
    await screen.findByTestId('nav-sidebar');
    expect(childLinkTexts()).toEqual([]);
  });

  it('lists Variables, Secrets and Datasets for the open application and highlights the current one', async () => {
    renderAt('/applications/app-1/secrets');
    await screen.findByTestId('nav-sidebar');
    await waitFor(() => expect(childLinkTexts()).toEqual(['Variables', 'Secrets', 'Datasets']));
    const nav = createWrapper(screen.getByTestId('nav-sidebar')).findSideNavigation()!;
    expect(nav.findLinkByHref('/applications/app-1/variables')).not.toBeNull();
    expect(nav.findLinkByHref('/applications/app-1/datasets')).not.toBeNull();
    expect(nav.findActiveLink()!.getElement()).toHaveAttribute('href', '/applications/app-1/secrets');
    // The route itself renders the Secrets page shell.
    expect(await screen.findByRole('heading', { name: 'Secrets' })).toBeInTheDocument();
  });

  it('lists the children on the application detail page as well', async () => {
    renderAt('/applications/app-1');
    await screen.findByTestId('nav-sidebar');
    await waitFor(() => expect(childLinkTexts()).toEqual(['Variables', 'Secrets', 'Datasets']));
  });
});
