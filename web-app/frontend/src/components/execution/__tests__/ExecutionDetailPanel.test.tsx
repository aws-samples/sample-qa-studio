/**
 * ExecutionDetailPanel — the body of the execution view (information, timeline,
 * steps, downloads, logs, stop) without the page chrome. Rendered by the
 * execution page today and by the split panel on the use case page later.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import createWrapper from '@cloudscape-design/components/test-utils/dom';

const apiGet = vi.fn();
const apiPost = vi.fn();
vi.mock('../../../utils/api', () => ({
  api: {
    get: (...a: unknown[]) => apiGet(...a),
    post: (...a: unknown[]) => apiPost(...a),
  },
}));
vi.mock('aws-amplify/auth', () => ({ fetchAuthSession: vi.fn() }));
// Children with external runtimes (DCV, rrweb, fetch of a presigned URL) are stubbed;
// each has its own tests.
vi.mock('../LiveViewPanel', () => ({
  default: (p: { currentStep: { sort: number } | null }) => (
    <div data-testid="live-view" data-current-step={p.currentStep?.sort ?? ''} />
  ),
}));
vi.mock('../../common/LogViewer', () => ({
  default: (p: { downloadUrl: string | null; loading?: boolean }) => (
    <div data-testid="log-viewer" data-url={p.downloadUrl ?? ''} data-loading={String(!!p.loading)} />
  ),
}));
vi.mock('../../RecordingPlayer', () => ({ RecordingPlayer: () => <div data-testid="recording-player" /> }));

import ExecutionDetailPanel from '../ExecutionDetailPanel';

const BASE = 'usecase/u1/executions/e1';

const finished = {
  sk: 'EXECUTION#e1', status: 'success', trigger_type: 'OnDemandHeadless', test_platform: 'web',
  created_at: '2025-01-01T00:00:00Z', executing_at: '2025-01-01T00:00:05Z', completed_at: '2025-01-01T00:01:00Z',
  starting_url: 'https://shop.test', nova_session_id: 'sess-1', region: 'eu-central-1',
};
const running = { ...finished, status: 'running', completed_at: undefined };

const STEPS = [
  { sk: 'EXECUTION_STEP#2', sort: 2, instruction: 'Add to cart', status: 'executing', step_type: 'navigation', logs: [] },
  { sk: 'EXECUTION_STEP#1', sort: 1, instruction: 'Open the shop', status: 'success', step_type: 'navigation', logs: [] },
];

type Overrides = { execution?: Record<string, unknown> | Error; variables?: unknown; artifacts?: unknown };

function mockApi({ execution = finished, variables, artifacts }: Overrides = {}) {
  apiGet.mockImplementation(async (endpoint: string) => {
    if (endpoint === BASE) {
      if (execution instanceof Error) throw execution;
      return execution;
    }
    if (endpoint === `${BASE}/steps`) return { steps: STEPS };
    if (endpoint === `${BASE}/variables`) {
      return variables ?? { variables: [], runtime_variables: [], execution_variables: {} };
    }
    if (endpoint === `${BASE}/downloads`) return { files: [] };
    if (endpoint === `${BASE}/artifacts`) return artifacts ?? { artifacts: [] };
    throw new Error(`unexpected GET ${endpoint}`);
  });
}

const executionFetches = () => apiGet.mock.calls.filter(([e]) => e === BASE).length;
const variablesFetches = () => apiGet.mock.calls.filter(([e]) => e === `${BASE}/variables`).length;
const stopButton = () => screen.queryByTestId('stop-execution-button');
// ExecutionSteps mounts its own (hidden) trace modal first, so the stop modal is looked up by test id.
const stopModal = () => createWrapper(document.body).findModal('[data-testid="stop-execution-modal"]')!;
const confirmStop = () => stopModal().findFooter()!.findButton('[data-testid="confirm-stop-button"]')!.getElement();

function renderPanel() {
  return render(<ExecutionDetailPanel usecaseId="u1" executionId="e1" />);
}

beforeEach(() => {
  apiGet.mockReset();
  apiPost.mockReset();
  apiPost.mockResolvedValue({});
});
afterEach(() => {
  vi.useRealTimers();
  cleanup();
});

describe('ExecutionDetailPanel — finished execution', () => {
  it('renders information, timeline and steps; no Stop button, no usecase or artifacts call', async () => {
    mockApi();
    renderPanel();
    expect(await screen.findByText('Execution Information')).toBeInTheDocument();
    expect(screen.getByText('https://shop.test')).toBeInTheDocument();
    expect(screen.getByText('Open the shop')).toBeInTheDocument();
    expect(screen.getByText('Add to cart')).toBeInTheDocument();
    expect(screen.getByText('Execution Timeline')).toBeInTheDocument();
    expect(stopButton()).not.toBeInTheDocument();
    expect(screen.queryByTestId('live-view')).not.toBeInTheDocument();
    expect(apiGet).not.toHaveBeenCalledWith('usecase/u1');
    expect(apiGet).not.toHaveBeenCalledWith(`${BASE}/artifacts`);
    expect(screen.queryByText('Execution Logs')).not.toBeInTheDocument();
  });

  it('sorts the steps by their sort value', async () => {
    mockApi();
    renderPanel();
    await screen.findByText('Open the shop');
    const rows = screen.getAllByText(/Open the shop|Add to cart/).map((e) => e.textContent);
    expect(rows).toEqual(['Open the shop', 'Add to cart']);
  });

  it('shows a Spinner while loading and "Execution not found" when the fetch fails', async () => {
    apiGet.mockImplementation(() => new Promise(() => undefined));
    const { container, unmount } = renderPanel();
    expect(createWrapper(container).findSpinner()).not.toBeNull();
    expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    unmount();

    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    mockApi({ execution: new Error('404') });
    renderPanel();
    expect(await screen.findByText('Execution not found')).toBeInTheDocument();
  });

  it('shows the CloudWatch Logs button only when the execution carries a URL', async () => {
    mockApi({ execution: { ...finished, cloudwatch_logs_url: 'https://logs.test' } });
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    renderPanel();
    fireEvent.click(await screen.findByTestId('cloudwatch-logs-button'));
    expect(open).toHaveBeenCalledWith('https://logs.test', '_blank');
    cleanup();

    mockApi();
    renderPanel();
    await screen.findByText('Execution Information');
    expect(screen.queryByTestId('cloudwatch-logs-button')).not.toBeInTheDocument();
  });

  it('renders the Variables card with the execution snapshot, fetched once by the panel', async () => {
    mockApi({
      variables: {
        variables: [{ key: 'USER', value: 'edited-later' }],
        runtime_variables: [],
        execution_variables: { USER: 'ann' },
      },
    });
    renderPanel();
    expect(await screen.findByText('Defined Variables')).toBeInTheDocument();
    expect(screen.getByText('ann')).toBeInTheDocument();
    expect(screen.queryByText('edited-later')).not.toBeInTheDocument();
    expect(variablesFetches()).toBe(1);
  });

  it('renders the Variables card for runtime variables alone', async () => {
    mockApi({
      variables: { variables: [], runtime_variables: [{ key: 'order_id', value: 'A-42' }], execution_variables: {} },
    });
    renderPanel();
    expect(await screen.findByText('Runtime Variables')).toBeInTheDocument();
    expect(screen.getByText('A-42')).toBeInTheDocument();
  });

  it('hides the Variables card when neither snapshot nor runtime variables exist', async () => {
    // Current use-case variables alone are not the run's values.
    mockApi({ variables: { variables: [{ key: 'USER', value: 'ann' }], runtime_variables: [], execution_variables: {} } });
    renderPanel();
    await screen.findByText('Execution Information');
    expect(screen.queryByText('Variables')).not.toBeInTheDocument();
    cleanup();

    mockApi();
    renderPanel();
    await screen.findByText('Execution Information');
    expect(screen.queryByText('Variables')).not.toBeInTheDocument();
  });

  it('hides the Variables card when the variables fetch fails', async () => {
    mockApi();
    const base = apiGet.getMockImplementation()!;
    apiGet.mockImplementation(async (endpoint: string) => {
      if (endpoint === `${BASE}/variables`) throw new Error('500');
      return base(endpoint);
    });
    renderPanel();
    await screen.findByText('Execution Information');
    expect(screen.queryByText('Variables')).not.toBeInTheDocument();
  });

  it('renders the Device Farm block for mobile executions', async () => {
    mockApi({ execution: { ...finished, test_platform: 'mobile', device_name: 'Pixel 8' } });
    renderPanel();
    expect(await screen.findByText('Device Farm Details')).toBeInTheDocument();
    expect(screen.getByText('Pixel 8')).toBeInTheDocument();
  });
});

describe('ExecutionDetailPanel — running execution', () => {
  it('shows Stop and the live view with the executing step, and polls every 10 s', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    mockApi({ execution: running });
    renderPanel();
    expect(await screen.findByTestId('stop-execution-button')).toBeInTheDocument();
    expect(screen.getByTestId('live-view')).toHaveAttribute('data-current-step', '2');
    expect(executionFetches()).toBe(1);

    await act(async () => {
      vi.advanceTimersByTime(10000);
    });
    await waitFor(() => expect(executionFetches()).toBe(2));
  });

  it('fetches /variables exactly once per poll cycle', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    mockApi({ execution: running, variables: { variables: [], runtime_variables: [], execution_variables: { a: '1' } } });
    renderPanel();
    expect(await screen.findByText('Defined Variables')).toBeInTheDocument();
    expect(variablesFetches()).toBe(1);

    for (const cycle of [2, 3]) {
      await act(async () => {
        vi.advanceTimersByTime(10000);
      });
      await waitFor(() => expect(executionFetches()).toBe(cycle));
      expect(variablesFetches()).toBe(cycle);
    }
  });

  it('shows runtime variables captured during the run after the next poll', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    let runtime: { key: string; value: string }[] = [];
    mockApi({ execution: running });
    const base = apiGet.getMockImplementation()!;
    apiGet.mockImplementation(async (endpoint: string) => {
      if (endpoint === `${BASE}/variables`) {
        return { variables: [], runtime_variables: runtime, execution_variables: { product: 'Laptop' } };
      }
      return base(endpoint);
    });
    renderPanel();
    expect(await screen.findByText('Defined Variables')).toBeInTheDocument();
    expect(screen.queryByText('Runtime Variables')).not.toBeInTheDocument();

    runtime = [{ key: 'order_id', value: 'A-42' }];
    await act(async () => {
      vi.advanceTimersByTime(10000);
    });
    expect(await screen.findByText('Runtime Variables')).toBeInTheDocument();
    expect(screen.getByText('A-42')).toBeInTheDocument();
  });

  it('confirming Stop posts to /stop and refetches', async () => {
    mockApi({ execution: running });
    renderPanel();
    fireEvent.click(await screen.findByTestId('stop-execution-button'));

    await waitFor(() => expect(stopModal().isVisible()).toBe(true));
    fireEvent.click(confirmStop());

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(`${BASE}/stop`, {}));
    await waitFor(() => expect(executionFetches()).toBe(2));
    await waitFor(() => expect(stopModal().isVisible()).toBe(false));
  });

  it('shows the stop error inside the modal and keeps it open', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    apiPost.mockRejectedValue(new Error('Task already stopped'));
    mockApi({ execution: running });
    renderPanel();
    fireEvent.click(await screen.findByTestId('stop-execution-button'));
    await waitFor(() => expect(stopModal().isVisible()).toBe(true));
    fireEvent.click(confirmStop());

    expect(await screen.findByText('Task already stopped')).toBeInTheDocument();
    expect(stopModal().isVisible()).toBe(true);
    expect(executionFetches()).toBe(1);
  });
});

describe('ExecutionDetailPanel — ci_runner logs', () => {
  it('requests the artifacts of a finished ci_runner execution and renders the LogViewer', async () => {
    mockApi({
      execution: { ...finished, trigger_type: 'ci_runner' },
      artifacts: { artifacts: [{ type: 'logs', download_url: 'https://logs.test/run.log' }] },
    });
    renderPanel();
    expect(await screen.findByText('Execution Logs')).toBeInTheDocument();
    expect(apiGet).toHaveBeenCalledWith(`${BASE}/artifacts`);
    await waitFor(() =>
      expect(screen.getByTestId('log-viewer')).toHaveAttribute('data-url', 'https://logs.test/run.log'),
    );
  });

  it('does not request artifacts while a ci_runner execution is still running', async () => {
    mockApi({ execution: { ...running, trigger_type: 'ci_runner' } });
    renderPanel();
    await screen.findByText('Execution Information');
    expect(apiGet).not.toHaveBeenCalledWith(`${BASE}/artifacts`);
  });
});
