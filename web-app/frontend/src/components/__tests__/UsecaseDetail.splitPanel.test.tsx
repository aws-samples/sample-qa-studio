/**
 * Use case page — the `execution` query parameter drives the selected row of the
 * Execution History table and a split panel on the root AppLayout that renders
 * ExecutionDetailPanel. Rendered through <App /> so the real router, the
 * SplitPanelProvider and the root layout are exercised.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
// The real module is kept for `executionIdOf`; only the request-making objects are replaced.
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
// Children with external runtimes (DCV, rrweb) are stubbed; each has its own tests.
vi.mock('../execution/LiveViewPanel', () => ({ default: () => <div data-testid="live-view" /> }));
vi.mock('../common/LogViewer', () => ({ default: () => <div data-testid="log-viewer" /> }));
vi.mock('../RecordingPlayer', () => ({ RecordingPlayer: () => <div data-testid="recording-player" /> }));

import App from '../../App';

const USECASE = { id: 'u1', name: 'Shop checkout', description: '', starting_url: 'https://shop.test',
  test_platform: 'web', active: true, created_at: '2025-01-01T00:00:00Z' };

const EXECUTIONS = [
  { pk: 'USECASE#u1', sk: 'EXECUTION#e1', status: 'success', created_at: '2025-01-02T00:00:00Z', trigger_type: 'OnDemand' },
  { pk: 'USECASE#u1', sk: 'EXECUTION#e2', status: 'failed', created_at: '2025-01-01T00:00:00Z', trigger_type: 'OnDemand' },
];

function execution(id: string) {
  return {
    sk: `EXECUTION#${id}`, status: id === 'e1' ? 'success' : 'failed', trigger_type: 'OnDemand', test_platform: 'web',
    created_at: '2025-01-01T00:00:00Z', executing_at: '2025-01-01T00:00:05Z', completed_at: '2025-01-01T00:01:00Z',
    starting_url: 'https://shop.test', nova_session_id: `sess-${id}`, region: 'eu-central-1',
  };
}

function steps(id: string) {
  return [
    { sk: `EXECUTION_STEP#${id}-1`, sort: 1, instruction: `Open the shop (${id})`, status: 'success', step_type: 'navigation', logs: [] },
    { sk: `EXECUTION_STEP#${id}-2`, sort: 2, instruction: `Add to cart (${id})`, status: 'success', step_type: 'navigation', logs: [] },
  ];
}

/** One routing table for every GET the page and the panel issue. Unknown paths fail the test. */
function mockApi() {
  apiGet.mockImplementation(async (endpoint: string) => {
    if (endpoint === 'usecase/u1') return USECASE;
    if (endpoint === 'usecase/u1/executions') return { executions: EXECUTIONS };
    if (endpoint === 'usecase/u1/steps') return { steps: [] };
    const exec = /^usecase\/u1\/executions\/(e\d)(?:\/(\w+))?$/.exec(endpoint);
    if (exec) {
      const [, id, sub] = exec;
      if (!sub) return execution(id);
      if (sub === 'steps') return { steps: steps(id) };
      if (sub === 'variables') return { variables: [], runtime_variables: [] };
      if (sub === 'downloads') return { files: [] };
      if (sub === 'artifacts') return { artifacts: [] };
    }
    throw new Error(`unexpected GET ${endpoint}`);
  });
}

function renderAt(path: string) {
  window.history.pushState({}, '', path);
  return render(<App />);
}

const splitPanel = () => createWrapper(document.body).findAppLayout()!.findSplitPanel();
const panelHeader = () => splitPanel()!.findHeader().getElement();

/** The Execution History table (the panel renders an "Execution Steps" table too). */
const historyTable = () =>
  createWrapper(document.body).findAllTables().find((t) => t.findHeaderSlot()?.getElement().textContent?.includes('Execution History'))!;
const historyRadio = (index: number) => historyTable().findRowSelectionArea(index)!.find('input')!.getElement() as HTMLInputElement;

/** Render and wait until the Execution History table lists both runs (lazy chunks + fetch). */
async function renderHistory(path: string) {
  renderAt(path);
  await waitFor(() => {
    expect(historyTable(), 'Execution History table').toBeDefined();
    expect(historyTable().findRows()).toHaveLength(EXECUTIONS.length);
  }, { timeout: 5000 });
}

async function expectPanelFor(id: string) {
  await waitFor(() => {
    expect(splitPanel(), 'split panel').not.toBeNull();
    expect(panelHeader()).toHaveTextContent(`Execution ${id}`);
  });
  expect(await screen.findByText(`Open the shop (${id})`)).toBeInTheDocument();
  expect(screen.getByText('Execution Steps')).toBeInTheDocument();
}

beforeEach(() => {
  apiGet.mockReset();
  mockApi();
  window.localStorage.clear();
});
afterEach(() => {
  cleanup();
  window.history.pushState({}, '', '/');
});

describe('Use case page — execution split panel', () => {
  it('opens the panel for ?execution=e1 with the execution header, the steps table and the selected row', async () => {
    await renderHistory('/usecase/u1?tab=history&execution=e1');
    await expectPanelFor('e1');
    expect(historyRadio(1).checked).toBe(true);
    expect(historyRadio(2).checked).toBe(false);
  });

  it('selecting another row rewrites the URL (replace) and swaps the panel content', async () => {
    await renderHistory('/usecase/u1?tab=history&execution=e1');
    await expectPanelFor('e1');
    const historyLength = window.history.length;

    fireEvent.click(historyRadio(2));

    await waitFor(() => expect(window.location.search).toBe('?tab=history&execution=e2'));
    await expectPanelFor('e2');
    expect(screen.queryByText('Open the shop (e1)')).not.toBeInTheDocument();
    expect(historyRadio(2).checked).toBe(true);
    expect(window.history.length).toBe(historyLength);
  });

  it('the panel close button removes execution from the URL and the panel', async () => {
    await renderHistory('/usecase/u1?tab=history&execution=e1');
    await expectPanelFor('e1');

    act(() => { splitPanel()!.findCloseButton()!.click(); });

    await waitFor(() => expect(window.location.search).toBe('?tab=history'));
    await waitFor(() => expect(splitPanel()).toBeNull());
    expect(historyTable().findSelectedRows()).toHaveLength(0);
  });

  it('keeps the panel open while switching to Workflow Steps, so steps and execution are side by side', async () => {
    await renderHistory('/usecase/u1?tab=history&execution=e1');
    await expectPanelFor('e1');

    act(() => { createWrapper(document.body).findTabs()!.findTabLinkByIndex(2)!.click(); });

    await waitFor(() => expect(window.location.search).toBe('?tab=steps&execution=e1'));
    await waitFor(() => expect(createWrapper(document.body).findTabs()!.findActiveTab()!.getElement()).toHaveTextContent('Workflow Steps'));
    expect(splitPanel()).not.toBeNull();
    expect(panelHeader()).toHaveTextContent('Execution e1');

    // Back on history the same row is still selected.
    act(() => { createWrapper(document.body).findTabs()!.findTabLinkByIndex(1)!.click(); });
    await waitFor(() => expect(window.location.search).toBe('?tab=history&execution=e1'));
    await waitFor(() => expect(historyTable().findRows()).toHaveLength(EXECUTIONS.length));
    expect(historyRadio(1).checked).toBe(true);
    expect(splitPanel()).not.toBeNull();
  });

  it('closing the panel on another tab drops execution and keeps the tab', async () => {
    renderAt('/usecase/u1?tab=steps&execution=e1');
    await expectPanelFor('e1');

    act(() => { splitPanel()!.findCloseButton()!.click(); });

    await waitFor(() => expect(window.location.search).toBe('?tab=steps'));
    await waitFor(() => expect(splitPanel()).toBeNull());
    expect(createWrapper(document.body).findTabs()!.findActiveTab()!.getElement()).toHaveTextContent('Workflow Steps');
  });

  it('renders no panel without an execution parameter', async () => {
    await renderHistory('/usecase/u1?tab=history');
    expect(splitPanel()).toBeNull();
    expect(historyTable().findSelectedRows()).toHaveLength(0);
    expect(apiGet).not.toHaveBeenCalledWith('usecase/u1/executions/e1');
  });

  it('opens the panel from a deep link on another tab', async () => {
    renderAt('/usecase/u1?tab=steps&execution=e1');
    // The name is shown in the breadcrumb and in the h1.
    expect(await screen.findAllByText('Shop checkout')).not.toHaveLength(0);
    await waitFor(() => expect(createWrapper(document.body).findTabs()!.findActiveTab()!.getElement()).toHaveTextContent('Workflow Steps'));
    await expectPanelFor('e1');
  });
});
