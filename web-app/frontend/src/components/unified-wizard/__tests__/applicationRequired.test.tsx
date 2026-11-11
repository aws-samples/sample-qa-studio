/**
 * Ported from the removed WizardApplicationRequired.test.tsx (WizardSetup,
 * CreateFromTemplate): the unified wizard sends the chosen application to
 * wizard/start (interactive) and templates/{id}/apply (template).
 */
import { useReducer } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';

import SetupAndRecordStep from '../steps/SetupAndRecordStep';
import ReviewAndCreateStep from '../steps/ReviewAndCreateStep';
import { initialWizardState, wizardReducer } from '../wizardReducer';
import type { WizardState } from '../types';

const apiPost = vi.fn();
const navigate = vi.fn();
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));
vi.mock('../../../utils/api', () => ({
  api: { post: (...a: unknown[]) => apiPost(...a), get: vi.fn().mockResolvedValue({ steps: [] }) },
  wizardApi: { addStep: vi.fn() },
  exportImportApi: { importUsecase: vi.fn() },
  devicesApi: { list: vi.fn().mockResolvedValue({ devices: [] }) },
}));
vi.mock('../../wizard/WizardLiveView', () => ({ default: () => <div data-testid="live-view" /> }));
vi.mock('../../wizard/WizardStepBuilder', () => ({ default: () => null }));
vi.mock('../../wizard/WizardStepsList', () => ({ default: () => null }));

function stateFor(creationMethod: 'interactive-wizard' | 'template'): WizardState {
  return {
    ...initialWizardState,
    creationPath: 'create-new',
    creationMethod,
    basicInfo: {
      ...initialWizardState.basicInfo,
      name: 'Login',
      startingUrl: 'https://e.test/',
      executionRegion: 'eu-central-1',
      modelId: 'nova-act-v1.0',
      applicationId: 'app-1',
    },
    templateConfig: { ...initialWizardState.templateConfig, selectedTemplateId: 't1' },
  };
}

function Harness({ initial, Step, submitTrigger = 0 }: {
  initial: WizardState; Step: typeof SetupAndRecordStep; submitTrigger?: number;
}) {
  const [state, dispatch] = useReducer(wizardReducer, initial);
  return <Step state={state} dispatch={dispatch} validationErrors={{}} submitTrigger={submitTrigger} />;
}

describe('the chosen application reaches the backend', () => {
  beforeEach(() => {
    apiPost.mockReset();
    navigate.mockReset();
  });

  it('interactive wizard: wizard/start carries application_id', async () => {
    apiPost.mockResolvedValue({ sessionId: 's-1', usecaseId: 'uc-1' });
    render(<Harness initial={stateFor('interactive-wizard')} Step={SetupAndRecordStep} />);

    const start = screen.getAllByRole('button').find((b) => /start/i.test(b.textContent || ''))!;
    await userEvent.click(start);

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('wizard/start', expect.objectContaining({
      application_id: 'app-1', starting_url: 'https://e.test/', executing_region: 'eu-central-1',
    })));
  });

  it('template: templates/{id}/apply carries application_id', async () => {
    apiPost.mockResolvedValue({ success: true, usecaseId: 'uc-new' });
    const initial = stateFor('template');
    const { rerender } = render(<Harness initial={initial} Step={ReviewAndCreateStep} />);
    rerender(<Harness initial={initial} Step={ReviewAndCreateStep} submitTrigger={1} />);

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('templates/t1/apply', expect.objectContaining({
      application_id: 'app-1', name: 'Login',
    })));
  });
});
