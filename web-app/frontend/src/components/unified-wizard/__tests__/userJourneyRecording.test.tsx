/**
 * Unified wizard — the user-journey method's optional browser recording and
 * missing-secret collection (parity with the removed /create/journey page).
 */
import { useReducer } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';

import DescribeAndGenerateStep from '../steps/DescribeAndGenerateStep';
import ReviewAndCreateStep from '../steps/ReviewAndCreateStep';
import { initialWizardState, wizardReducer } from '../wizardReducer';
import { validateDescribeAndGenerate } from '../validation';
import type { WizardState } from '../types';

const apiPost = vi.fn();
const generateUsecase = vi.fn();
const importUsecase = vi.fn();
const navigate = vi.fn();
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));
vi.mock('../../../utils/api', () => ({
  api: { post: (...a: unknown[]) => apiPost(...a), get: vi.fn() },
  wizardApi: { generateUsecase: (...a: unknown[]) => generateUsecase(...a) },
  exportImportApi: { importUsecase: (...a: unknown[]) => importUsecase(...a) },
  devicesApi: { list: vi.fn().mockResolvedValue({ devices: [] }) },
}));

const RECORDING = { type: 'cdp_actions', version: '1.0', data: { session: { startedAt: 0, stoppedAt: 5000, actions: [] } } };

// The live view needs DCV; the stub only exposes the two callbacks.
vi.mock('../../UserJourneyWizard/BrowserSessionPanel', () => ({
  default: ({ onRecordingComplete, onSessionEnd }: { onRecordingComplete: (d: unknown) => void; onSessionEnd: () => void }) => (
    <div data-testid="browser-session">
      <button onClick={() => onRecordingComplete(RECORDING)}>finish recording</button>
      <button onClick={onSessionEnd}>end session</button>
    </div>
  ),
}));
vi.mock('../../UserJourneyWizard/RecordingSummary', () => ({
  default: () => <div data-testid="recording-summary" />,
}));

function journeyState(partial: Partial<WizardState> = {}): WizardState {
  return {
    ...initialWizardState,
    creationPath: 'create-new',
    creationMethod: 'user-journey',
    basicInfo: {
      ...initialWizardState.basicInfo,
      name: 'Checkout',
      startingUrl: 'https://shop.test/',
      executionRegion: 'eu-central-1',
      modelId: 'nova-act-v1.0',
      applicationId: 'app-1',
    },
    ...partial,
  };
}

function Describe({ initial }: { initial: WizardState }) {
  const [state, dispatch] = useReducer(wizardReducer, initial);
  return <DescribeAndGenerateStep state={state} dispatch={dispatch} validationErrors={{}} />;
}

describe('user journey — browser recording', () => {
  beforeEach(() => {
    apiPost.mockReset();
    generateUsecase.mockReset();
    apiPost.mockImplementation(async (path: string) =>
      path === 'wizard/start' ? { sessionId: 's-1', usecaseId: 'rec-uc' } : {});
  });

  it('starts a recording session for the selected application and terminates it on "end session"', async () => {
    const user = userEvent.setup();
    render(<Describe initial={journeyState()} />);

    await user.click(screen.getByRole('button', { name: 'Start Browser Session' }));

    expect(apiPost).toHaveBeenCalledWith('wizard/start', expect.objectContaining({
      application_id: 'app-1', starting_url: 'https://shop.test/', executing_region: 'eu-central-1',
    }));
    await user.click(await screen.findByRole('button', { name: 'end session' }));
    expect(apiPost).toHaveBeenCalledWith('wizard/s-1/terminate/rec-uc', {});
    expect(screen.getByRole('button', { name: 'Start Browser Session' })).toBeInTheDocument();
  });

  it('sends the recording to the generator and allows generating without a description', async () => {
    generateUsecase.mockResolvedValue({ success: true, usecaseData: JSON.stringify({ usecase: { name: 'x' }, steps: [] }) });
    const user = userEvent.setup();
    render(<Describe initial={journeyState()} />);

    await user.click(screen.getByRole('button', { name: 'Start Browser Session' }));
    await user.click(await screen.findByRole('button', { name: 'finish recording' }));
    expect(screen.getByTestId('recording-summary')).toBeInTheDocument();

    const generate = screen.getByRole('button', { name: 'Generate' });
    expect(generate).toBeEnabled();
    await user.click(generate);

    await waitFor(() => expect(generateUsecase).toHaveBeenCalled());
    expect(generateUsecase.mock.calls[0][0]).toMatchObject({ recording_data: RECORDING, starting_url: 'https://shop.test/' });
    // Generating ends the live browser session.
    expect(apiPost).toHaveBeenCalledWith('wizard/s-1/terminate/rec-uc', {});
  });

  it('terminates a still-open session when the step unmounts', async () => {
    const user = userEvent.setup();
    const { unmount } = render(<Describe initial={journeyState()} />);
    await user.click(screen.getByRole('button', { name: 'Start Browser Session' }));
    await screen.findByTestId('browser-session');

    unmount();

    expect(apiPost).toHaveBeenCalledWith('wizard/s-1/terminate/rec-uc', {});
  });

  it('offers no recording for mobile', () => {
    render(<Describe initial={journeyState({ testPlatform: 'mobile', mobilePlatform: 'ANDROID' })} />);
    expect(screen.queryByRole('button', { name: 'Start Browser Session' })).not.toBeInTheDocument();
  });

  it('validation: a recording can stand in for the description', () => {
    const generated = { ...initialWizardState.userJourneyConfig, generatedUsecase: { steps: [] } };
    expect(validateDescribeAndGenerate(journeyState({ userJourneyConfig: generated })).userJourneyText).toBeDefined();
    expect(validateDescribeAndGenerate(journeyState({
      userJourneyConfig: { ...generated, recordingData: RECORDING as any },
    })).userJourneyText).toBeUndefined();
  });
});

describe('user journey — review collects missing secrets', () => {
  beforeEach(() => {
    apiPost.mockReset();
    importUsecase.mockReset();
    navigate.mockReset();
  });

  function Review({ submitTrigger }: { submitTrigger: number }) {
    const [state, dispatch] = useReducer(wizardReducer, journeyState({
      userJourneyConfig: { ...initialWizardState.userJourneyConfig, generatedUsecase: { usecase: { name: 'Checkout' }, steps: [] } },
    }));
    return <ReviewAndCreateStep state={state} dispatch={dispatch} validationErrors={{}} submitTrigger={submitTrigger} />;
  }

  it('shows the secrets form for generated secret steps, then stores the values', async () => {
    importUsecase.mockResolvedValue({ success: true, usecaseId: 'uc-new', missingSecrets: ['password'] });
    apiPost.mockResolvedValue({ message: 'ok' });
    const { rerender } = render(<Review submitTrigger={0} />);
    rerender(<Review submitTrigger={1} />);

    expect(await screen.findByText('Configure secrets')).toBeInTheDocument();
    expect(importUsecase).toHaveBeenCalledWith(expect.objectContaining({ application_id: 'app-1' }));
    expect(navigate).not.toHaveBeenCalled();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('password'), 'pw');
    await user.click(screen.getByRole('button', { name: 'Save secrets' }));

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/usecase/uc-new'));
    expect(apiPost).toHaveBeenCalledWith('usecase/uc-new/secrets', { secrets: [{ key: 'password', value: 'pw' }] });
  });

  it('navigates straight to the use case when nothing is missing', async () => {
    importUsecase.mockResolvedValue({ success: true, usecaseId: 'uc-new' });
    const { rerender } = render(<Review submitTrigger={0} />);
    rerender(<Review submitTrigger={1} />);
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/usecase/uc-new'));
  });
});
