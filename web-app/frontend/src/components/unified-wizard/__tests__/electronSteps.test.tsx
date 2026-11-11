import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import PlatformSelectionStep from '../steps/PlatformSelectionStep';
import PlatformConfigStep from '../steps/PlatformConfigStep';
import ReviewAndCreateStep from '../steps/ReviewAndCreateStep';
import { initialWizardState } from '../wizardReducer';
import type { WizardState } from '../types';

const apiPost = vi.fn();
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('../../../utils/api', () => ({
  api: { post: (...a: unknown[]) => apiPost(...a), get: vi.fn() },
  exportImportApi: { importUsecase: vi.fn() },
  devicesApi: { list: vi.fn().mockResolvedValue({ devices: [] }) },
}));

function electronState(partial: Partial<WizardState> = {}): WizardState {
  return {
    ...initialWizardState,
    creationPath: 'create-new',
    creationMethod: 'blank',
    testPlatform: 'electron',
    basicInfo: {
      ...initialWizardState.basicInfo,
      name: 'Harness smoke',
      executionRegion: 'eu-central-1',
      modelId: 'nova-act-v1.0',
      applicationId: 'app-1',
    },
    ...partial,
  };
}

describe('unified wizard — electron step components', () => {
  beforeEach(() => apiPost.mockReset());

  it('offers an Electron tile', async () => {
    const dispatch = vi.fn();
    render(<PlatformSelectionStep state={initialWizardState} dispatch={dispatch} validationErrors={{}} />);
    await userEvent.click(screen.getByText('Electron'));
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_TEST_PLATFORM', payload: 'electron' });
  });

  it('app configuration shows the CI-runner notice and an optional bundle id', async () => {
    const dispatch = vi.fn();
    render(<PlatformConfigStep state={electronState()} dispatch={dispatch} validationErrors={{}} />);
    expect(screen.getByText('Runs through the CI runner only')).toBeInTheDocument();
    expect(screen.queryByText('Mobile platform')).not.toBeInTheDocument();
    expect(screen.queryByText(/Step caching/)).not.toBeInTheDocument();
    await userEvent.type(screen.getByPlaceholderText('com.example.desktop'), 'c');
    expect(dispatch).toHaveBeenCalledWith({ type: 'UPDATE_BLANK_CONFIG', payload: { bundleId: 'c' } });
  });

  it('review submits test_platform=electron with bundle_id and no starting_url', async () => {
    apiPost.mockResolvedValue({ id: 'u-new' });
    const state = electronState({
      blankConfig: { ...initialWizardState.blankConfig, bundleId: 'com.productharness.desktop' },
    });
    // The step submits when submitTrigger changes after mount (the wizard's Create button).
    const { rerender } = render(
      <ReviewAndCreateStep state={state} dispatch={vi.fn()} validationErrors={{}} submitTrigger={0} />,
    );
    expect(screen.getAllByText('Electron').length).toBeGreaterThan(0);
    expect(screen.getByText(/CI runner only/)).toBeInTheDocument();
    expect(screen.getByText('com.productharness.desktop')).toBeInTheDocument();
    rerender(<ReviewAndCreateStep state={state} dispatch={vi.fn()} validationErrors={{}} submitTrigger={1} />);
    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    const [path, payload] = apiPost.mock.calls[0];
    expect(path).toBe('usecase');
    expect(payload.test_platform).toBe('electron');
    expect(payload.bundle_id).toBe('com.productharness.desktop');
    expect(payload).not.toHaveProperty('starting_url');
    expect(payload).not.toHaveProperty('platform');
  });

  it('review omits bundle_id when empty', async () => {
    apiPost.mockResolvedValue({ id: 'u-new' });
    const state = electronState();
    const { rerender } = render(
      <ReviewAndCreateStep state={state} dispatch={vi.fn()} validationErrors={{}} submitTrigger={0} />,
    );
    rerender(<ReviewAndCreateStep state={state} dispatch={vi.fn()} validationErrors={{}} submitTrigger={1} />);
    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    expect(apiPost.mock.calls[0][1]).not.toHaveProperty('bundle_id');
  });
});
