/**
 * WorkflowSteps — application datasets plumbing: the use case definition
 * provides `application_id`, the dataset list is fetched once and both reach
 * the step cards and the create modal.
 */
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

const { apiGet, datasetsApi, cardProps, modalProps } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  datasetsApi: { list: vi.fn() },
  cardProps: vi.fn(),
  modalProps: vi.fn(),
}));

vi.mock('../../../utils/api', () => ({
  api: { get: apiGet, post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  datasetsApi,
}));
vi.mock('../../WorkflowStepsCard', () => ({
  default: (props: any) => { cardProps(props); return <div data-testid="cards" />; },
}));
vi.mock('../StepFormModal', () => ({
  default: (props: any) => { modalProps(props); return null; },
}));
vi.mock('../../templates/ImportTemplateModal', () => ({ default: () => null }));

import WorkflowSteps from '../WorkflowSteps';

const STEPS = [{ pk: 'USECASE#u', sk: 'STEP#R2', id: 'R2', usecaseId: 'u', sort: 1, instruction: 'Each customer', step_type: 'repeat', dataset_id: 'ds-1' }];
const DATASETS = [{ dataset_id: 'ds-1', name: 'customers', description: '', column_count: 3, row_count: 5, updated_at: '' }];

function mockApi(usecase: Record<string, unknown>) {
  apiGet.mockImplementation((path: string) => {
    if (path === 'usecase/u/steps') return Promise.resolve({ steps: STEPS });
    if (path === 'usecase/u') return Promise.resolve(usecase);
    return Promise.reject(new Error(`unexpected GET ${path}`));
  });
}

beforeEach(() => {
  apiGet.mockReset();
  datasetsApi.list.mockReset();
  cardProps.mockClear();
  modalProps.mockClear();
});
afterEach(() => { cleanup(); });

describe('WorkflowSteps — application datasets', () => {
  it('lists the datasets of the use case application once and passes them with the id to the cards and the modal', async () => {
    mockApi({ id: 'u', name: 'UC', application_id: 'app-1' });
    datasetsApi.list.mockResolvedValue({ datasets: DATASETS });
    render(<WorkflowSteps usecaseId="u" />);
    await screen.findByTestId('cards');
    await waitFor(() => expect(cardProps).toHaveBeenCalledWith(expect.objectContaining({ applicationId: 'app-1', datasets: DATASETS })));
    expect(modalProps).toHaveBeenCalledWith(expect.objectContaining({ applicationId: 'app-1', datasets: DATASETS }));
    expect(datasetsApi.list).toHaveBeenCalledTimes(1);
    expect(datasetsApi.list).toHaveBeenCalledWith('app-1');
  });

  it('passes no application and an empty list when the use case has no application_id', async () => {
    mockApi({ id: 'u', name: 'UC' });
    render(<WorkflowSteps usecaseId="u" />);
    await screen.findByTestId('cards');
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('usecase/u'));
    expect(datasetsApi.list).not.toHaveBeenCalled();
    const last = cardProps.mock.calls.at(-1)![0];
    expect(last.applicationId).toBeUndefined();
    expect(last.datasets).toEqual([]);
  });

  it('keeps the application id with an empty list when the dataset list fails', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    mockApi({ id: 'u', name: 'UC', application_id: 'app-1' });
    datasetsApi.list.mockRejectedValue(new Error('403'));
    render(<WorkflowSteps usecaseId="u" />);
    await screen.findByTestId('cards');
    await waitFor(() => expect(error).toHaveBeenCalled());
    await waitFor(() => expect(cardProps).toHaveBeenCalledWith(expect.objectContaining({ applicationId: 'app-1', datasets: [] })));
    error.mockRestore();
  });
});

describe('WorkflowSteps — header', () => {
  it('always renders the cards with Import Template and Add Step and no layout toggle', async () => {
    mockApi({ id: 'u', name: 'UC' });
    render(<WorkflowSteps usecaseId="u" />);
    await screen.findByTestId('cards');
    expect(screen.getByRole('button', { name: 'Import Template' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add Step' })).toBeInTheDocument();
    expect(screen.queryByText(/card layout/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });
});
