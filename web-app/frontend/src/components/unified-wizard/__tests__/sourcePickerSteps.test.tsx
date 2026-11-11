/**
 * SelectSourceStep / SelectTemplateStep on SourcePicker: list loading, the
 * dispatches on select and on detail load, previews, and dropping a detail
 * response for a selection that is no longer current.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, cleanup, render, renderHook, screen, waitFor } from '@testing-library/react';

const apiGet = vi.fn();
vi.mock('../../../utils/api', () => ({ api: { get: (...a: unknown[]) => apiGet(...a) } }));

import SelectSourceStep from '../steps/SelectSourceStep';
import SelectTemplateStep from '../steps/SelectTemplateStep';
import { useSourceDetail } from '../steps/SourcePicker';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

const cloneState = (overrides: Record<string, unknown> = {}) =>
  ({ cloneConfig: { selectedUsecaseId: null, usecaseDetail: null, newName: '', ...overrides } }) as any;
const templateState = (overrides: Record<string, unknown> = {}) =>
  ({ templateConfig: { selectedTemplateId: null, templateDetail: null, ...overrides } }) as any;

let consoleError: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  apiGet.mockReset();
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
});
afterEach(() => {
  cleanup();
  consoleError.mockRestore();
});

describe('SelectSourceStep', () => {
  it('shows a list load error', async () => {
    apiGet.mockRejectedValue(new Error('No access'));
    render(<SelectSourceStep state={cloneState()} dispatch={vi.fn()} validationErrors={{}} />);
    expect(await screen.findByText('No access')).toBeInTheDocument();
  });

  it('loads the detail of the selected use case and proposes a copy name', async () => {
    apiGet.mockImplementation(async (path: string) => {
      if (path === 'usecases') return { usecases: [{ id: 'u1', name: 'Login' }] };
      if (path === 'usecase/u1') return { id: 'u1', name: 'Login', active: true };
      if (path === 'usecase/u1/steps') return { steps: [{}, {}] };
      throw new Error('optional part down');
    });
    const dispatch = vi.fn();
    render(<SelectSourceStep state={cloneState({ selectedUsecaseId: 'u1' })} dispatch={dispatch} validationErrors={{}} />);

    await waitFor(() =>
      expect(dispatch).toHaveBeenCalledWith({
        type: 'UPDATE_CLONE_CONFIG',
        payload: {
          usecaseDetail: { id: 'u1', name: 'Login', active: true, steps: [{}, {}], variables: [], headers: {} },
          newName: 'Login (Copy)',
        },
      }),
    );
    expect(screen.getByText('Use case summary')).toBeInTheDocument();
  });

  it('renders the use case summary', async () => {
    apiGet.mockResolvedValue({ usecases: [] });
    const detail = {
      id: 'u1', name: 'Login', active: false, starting_url: 'https://x', description: 'Signs in',
      tags: ['smoke'], steps: [{}], variables: [{}, {}], headers: { a: '1' },
    };
    render(
      <SelectSourceStep
        state={cloneState({ selectedUsecaseId: 'u1', usecaseDetail: detail, newName: 'Login (Copy)' })}
        dispatch={vi.fn()}
        validationErrors={{}}
      />,
    );
    // The detail is re-fetched for the selection; the preview shows once that settles.
    expect(await screen.findByText('Inactive')).toBeInTheDocument();
    expect(screen.getByText('https://x')).toBeInTheDocument();
    expect(screen.getByText('1 step(s)')).toBeInTheDocument();
    expect(screen.getByText('2 variable(s)')).toBeInTheDocument();
    expect(screen.getByText('1 header(s)')).toBeInTheDocument();
    expect(screen.getByText('smoke')).toBeInTheDocument();
    expect(screen.getByText('Signs in')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Login (Copy)')).toBeInTheDocument();
  });
});

describe('SelectTemplateStep', () => {
  it('loads the template detail and prefills URL and description', async () => {
    apiGet.mockImplementation(async (path: string) => {
      if (path === 'templates') return { templates: [{ id: 't1', name: 'Checkout' }] };
      if (path === 'templates/t1') return { id: 't1', name: 'Checkout', starting_url: 'https://shop', description: 'Buys' };
      if (path === 'templates/t1/steps') return { steps: [] };
      if (path === 'templates/t1/variables') return { variables: [{ name: 'card' }] };
      throw new Error(`unexpected GET ${path}`);
    });
    const dispatch = vi.fn();
    render(<SelectTemplateStep state={templateState({ selectedTemplateId: 't1' })} dispatch={dispatch} validationErrors={{}} />);

    await waitFor(() =>
      expect(dispatch).toHaveBeenCalledWith({
        type: 'UPDATE_TEMPLATE_CONFIG',
        payload: {
          templateDetail: {
            id: 't1', name: 'Checkout', starting_url: 'https://shop', description: 'Buys', steps: [], variables: [{ name: 'card' }],
          },
          startingUrl: 'https://shop',
          description: 'Buys',
        },
      }),
    );
  });

  it('hides the "template" marker tag in the preview', async () => {
    apiGet.mockResolvedValue({ templates: [] });
    const detail = { id: 't1', name: 'Checkout', description: '', tags: ['Template', 'payments'] };
    render(
      <SelectTemplateStep state={templateState({ selectedTemplateId: 't1', templateDetail: detail })} dispatch={vi.fn()} validationErrors={{}} />,
    );
    expect(await screen.findByText('payments')).toBeInTheDocument();
    // "Template" remains only as the form field label, not as a tag badge.
    expect(screen.getAllByText('Template')).toHaveLength(1);
    expect(screen.getByText('payments').parentElement?.textContent).toBe('payments');
  });
});

describe('useSourceDetail', () => {
  it('drops a response for a selection that is no longer current', async () => {
    const first = deferred<string>();
    const second = deferred<string>();
    const fetchDetail = vi.fn((id: string) => (id === 'a' ? first.promise : second.promise));
    const onLoaded = vi.fn();

    const { result, rerender } = renderHook(({ id }) => useSourceDetail(id, fetchDetail, onLoaded), {
      initialProps: { id: 'a' as string | null },
    });
    expect(result.current).toBe(true);
    rerender({ id: 'b' });

    await act(async () => {
      second.resolve('detail-b');
      await second.promise;
    });
    await act(async () => {
      first.resolve('detail-a');
      await first.promise;
    });

    expect(onLoaded).toHaveBeenCalledTimes(1);
    expect(onLoaded).toHaveBeenCalledWith('detail-b');
    expect(result.current).toBe(false);
  });

  it('does nothing without a selection and stops loading when it is cleared', async () => {
    const pending = deferred<string>();
    const fetchDetail = vi.fn(() => pending.promise);
    const { result, rerender } = renderHook(({ id }) => useSourceDetail(id, fetchDetail, vi.fn()), {
      initialProps: { id: null as string | null },
    });
    expect(fetchDetail).not.toHaveBeenCalled();
    expect(result.current).toBe(false);

    rerender({ id: 'a' });
    expect(result.current).toBe(true);
    rerender({ id: null });
    expect(result.current).toBe(false);
  });

  it('logs a failed load and stops loading', async () => {
    const fetchDetail = vi.fn().mockRejectedValue(new Error('down'));
    const onLoaded = vi.fn();
    const { result } = renderHook(() => useSourceDetail('a', fetchDetail, onLoaded));
    await waitFor(() => expect(result.current).toBe(false));
    expect(onLoaded).not.toHaveBeenCalled();
    expect(consoleError).toHaveBeenCalled();
  });
});
