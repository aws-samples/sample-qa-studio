/**
 * The standalone execution page is gone; its URL
 * `/usecase/:usecaseId/execution/:executionId` redirects (replace) to the use
 * case page with the execution split panel open. Rendered through <App /> so
 * the real route table is exercised.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import createWrapper from '@cloudscape-design/components/test-utils/dom';

vi.mock('aws-amplify', () => ({ Amplify: { configure: vi.fn() } }));
vi.mock('aws-amplify/auth', () => ({ fetchAuthSession: vi.fn() }));
vi.mock('@aws-amplify/ui-react', () => ({
  Authenticator: ({ children }: { children: (p: { signOut: () => void; user: unknown }) => React.ReactNode }) =>
    <>{children({ signOut: vi.fn(), user: { username: 'tester' } })}</>,
}));
vi.mock('@aws-amplify/ui-react/styles.css', () => ({}));
vi.mock('../../amplifyconfiguration.json', () => ({ default: {} }));
vi.mock('../../auth', async () => {
  const access = await vi.importActual<typeof import('../../auth/applicationAccess')>('../../auth/applicationAccess');
  return {
    ...access,
    PermissionsProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    usePermissions: () => ({ isAdmin: false, isTeamLead: false, teams: [], hasScope: () => false, scopes: [], isLoading: false }),
  };
});

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock('../../utils/api', async () => {
  const actual = await vi.importActual<typeof import('../../utils/api')>('../../utils/api');
  return {
    ...actual,
    api: {
      get: (...a: unknown[]) => apiGet(...a),
      post: vi.fn().mockResolvedValue({}),
      patch: vi.fn().mockResolvedValue({}),
      put: vi.fn().mockResolvedValue({}),
      delete: vi.fn().mockResolvedValue(null),
    },
    subscriptionApi: {
      getStatus: vi.fn().mockResolvedValue({ is_subscribed: false }),
      subscribe: vi.fn(),
      unsubscribe: vi.fn(),
    },
  };
});
vi.mock('../execution/LiveViewPanel', () => ({ default: () => <div data-testid="live-view" /> }));
vi.mock('../common/LogViewer', () => ({ default: () => <div data-testid="log-viewer" /> }));
vi.mock('../RecordingPlayer', () => ({ RecordingPlayer: () => <div data-testid="recording-player" /> }));

import App from '../../App';

const USECASE = { id: 'u1', name: 'Shop checkout', description: '', starting_url: 'https://shop.test',
  test_platform: 'web', active: true, created_at: '2025-01-01T00:00:00Z' };
const EXECUTION = {
  sk: 'EXECUTION#e1', status: 'success', trigger_type: 'OnDemand', test_platform: 'web',
  created_at: '2025-01-02T00:00:00Z', executing_at: '2025-01-02T00:00:05Z', completed_at: '2025-01-02T00:01:00Z',
  starting_url: 'https://shop.test', nova_session_id: 'sess-e1', region: 'eu-central-1',
};

/** Every GET the landing page and its panel issue. Unknown paths fail the test. */
function mockApi() {
  apiGet.mockImplementation(async (endpoint: string) => {
    if (endpoint === 'usecase/u1') return USECASE;
    if (endpoint === 'usecase/u1/executions') return { executions: [{ ...EXECUTION, pk: 'USECASE#u1' }] };
    if (endpoint === 'usecase/u1/steps') return { steps: [] };
    if (endpoint === 'usecase/u1/executions/e1') return EXECUTION;
    if (endpoint === 'usecase/u1/executions/e1/steps') return { steps: [] };
    if (endpoint === 'usecase/u1/executions/e1/variables') return { variables: [], runtime_variables: [] };
    if (endpoint === 'usecase/u1/executions/e1/downloads') return { files: [] };
    if (endpoint === 'usecase/u1/executions/e1/artifacts') return { artifacts: [] };
    throw new Error(`unexpected GET ${endpoint}`);
  });
}

function renderAt(path: string) {
  window.history.pushState({}, '', path);
  const historyLength = window.history.length;
  render(<App />);
  return { historyLength };
}

const splitPanel = () => createWrapper(document.body).findAppLayout()!.findSplitPanel();

beforeEach(() => {
  apiGet.mockReset();
  mockApi();
  window.localStorage.clear();
});
afterEach(() => {
  cleanup();
  window.history.pushState({}, '', '/');
});

describe('Old execution URL', () => {
  it('redirects /usecase/:u/execution/:e to the use case page with the panel open, replacing the history entry', async () => {
    const { historyLength } = renderAt('/usecase/u1/execution/e1');

    await waitFor(() => expect(window.location.pathname).toBe('/usecase/u1'));
    expect(window.location.search).toBe('?tab=history&execution=e1');
    expect(window.history.length).toBe(historyLength);

    // The landing page is the use case page with the execution split panel.
    expect(await screen.findAllByText('Shop checkout')).not.toHaveLength(0);
    await waitFor(() => {
      expect(splitPanel(), 'split panel').not.toBeNull();
      expect(splitPanel()!.findHeader().getElement()).toHaveTextContent('Execution e1');
    }, { timeout: 5000 });
    // No standalone page: nothing renders the old "Execution Details" h1.
    expect(screen.queryByRole('heading', { name: 'Execution Details' })).not.toBeInTheDocument();
  });
});
