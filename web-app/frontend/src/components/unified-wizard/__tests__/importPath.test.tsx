/**
 * Unified wizard — import path parity with the removed /create/import page:
 * application and optional execution-region override reach POST /import.
 */
import { useReducer } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';

import ReviewAndCreateStep from '../steps/ReviewAndCreateStep';
import UploadFileStep from '../steps/UploadFileStep';
import { initialWizardState, wizardReducer } from '../wizardReducer';
import type { WizardState } from '../types';

const importUsecase = vi.fn();
const navigate = vi.fn();
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));
vi.mock('../../../utils/api', () => ({
  api: { post: vi.fn(), get: vi.fn().mockResolvedValue({ applications: [] }) },
  exportImportApi: { importUsecase: (...a: unknown[]) => importUsecase(...a) },
  devicesApi: { list: vi.fn().mockResolvedValue({ devices: [] }) },
}));
vi.mock('../../common/ApplicationSelect', () => ({ default: () => <div data-testid="application-select" /> }));

const EXPORT = { exportVersion: '1.0', usecase: { name: 'Login', executing_region: 'us-east-1' }, steps: [], variables: [], secrets: [] };

function importState(executionRegion: string): WizardState {
  return {
    ...initialWizardState,
    creationPath: 'import',
    basicInfo: { ...initialWizardState.basicInfo, applicationId: 'app-1', executionRegion },
    importConfig: {
      ...initialWizardState.importConfig,
      // jsdom's File has no .text(); the step only reads name + text().
      file: { name: 'login.json', size: 100, type: 'application/json', lastModified: 0,
              text: async () => JSON.stringify(EXPORT) } as unknown as File,
    },
  };
}

function Review({ initial, submitTrigger }: { initial: WizardState; submitTrigger: number }) {
  const [state, dispatch] = useReducer(wizardReducer, initial);
  return <ReviewAndCreateStep state={state} dispatch={dispatch} validationErrors={{}} submitTrigger={submitTrigger} />;
}

async function submit(initial: WizardState) {
  const { rerender } = render(<Review initial={initial} submitTrigger={0} />);
  rerender(<Review initial={initial} submitTrigger={1} />);
  await waitFor(() => expect(importUsecase).toHaveBeenCalled());
  return importUsecase.mock.calls[0][0];
}

describe('unified wizard — import', () => {
  beforeEach(() => {
    importUsecase.mockReset();
    importUsecase.mockResolvedValue({ success: true, usecaseId: 'uc-new' });
    navigate.mockReset();
  });

  it('sends the chosen application and the region override', async () => {
    const body = await submit(importState('eu-central-1'));
    expect(body).toMatchObject({ application_id: 'app-1', regionOverride: 'eu-central-1', usecase: { name: 'Login' } });
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/usecase/uc-new'));
  });

  it('keeps the file region when no override is chosen', async () => {
    const body = await submit(importState(''));
    expect(body).not.toHaveProperty('regionOverride');
  });

  it('the upload step offers the optional region select', async () => {
    const dispatch = vi.fn();
    render(<UploadFileStep state={importState('')} dispatch={dispatch} validationErrors={{}} />);
    expect(screen.getByText('Execution region (optional)')).toBeInTheDocument();
    await userEvent.click(screen.getByText("Keep the file's region"));
    const option = (await screen.findAllByRole('option'))[0];
    await userEvent.click(option);
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({
      type: 'UPDATE_BASIC_INFO', payload: { executionRegion: expect.any(String) },
    }));
  });
});
