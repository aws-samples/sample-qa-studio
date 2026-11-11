import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import {
  useBatchDelete,
  deleteInProgressFlash,
  deleteResultFlashes,
  USECASE_DELETE_NOUN,
  USECASE_DELETE_CONSEQUENCES,
} from '../useBatchDelete';

vi.mock('../../utils/api', () => ({
  api: {
    delete: vi.fn(),
  },
}));

import { api } from '../../utils/api';

const mockDelete = vi.mocked(api.delete);

describe('useBatchDelete', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('deletes every use case and reports success per item', async () => {
    mockDelete.mockResolvedValue(undefined);
    const { result } = renderHook(() => useBatchDelete());

    let results: any;
    await act(async () => {
      results = await result.current.deleteBatch([
        { id: 'uc-1', name: 'Login' },
        { id: 'uc-2', name: 'Checkout' },
      ]);
    });

    expect(results).toEqual([
      { usecaseId: 'uc-1', usecaseName: 'Login', success: true },
      { usecaseId: 'uc-2', usecaseName: 'Checkout', success: true },
    ]);
    expect(mockDelete).toHaveBeenCalledTimes(2);
    expect(mockDelete).toHaveBeenCalledWith('usecase/uc-1');
    expect(mockDelete).toHaveBeenCalledWith('usecase/uc-2');
  });

  it('keeps going after a failure and carries the error message', async () => {
    mockDelete
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error('Forbidden'))
      .mockResolvedValueOnce(undefined);
    const { result } = renderHook(() => useBatchDelete());

    let results: any;
    await act(async () => {
      results = await result.current.deleteBatch([
        { id: 'uc-1', name: 'A' },
        { id: 'uc-2', name: 'B' },
        { id: 'uc-3', name: 'C' },
      ]);
    });

    expect(results.map((r: any) => r.success)).toEqual([true, false, true]);
    expect(results[1]).toEqual({ usecaseId: 'uc-2', usecaseName: 'B', success: false, error: 'Forbidden' });
  });

  it('marks all as failed when every delete fails', async () => {
    mockDelete.mockRejectedValue(new Error('Service unavailable'));
    const { result } = renderHook(() => useBatchDelete());

    let results: any;
    await act(async () => {
      results = await result.current.deleteBatch([
        { id: 'uc-1', name: 'A' },
        { id: 'uc-2', name: 'B' },
      ]);
    });

    expect(results.every((r: any) => !r.success && r.error === 'Service unavailable')).toBe(true);
  });

  it('sends the deletes in batches of the configured Lambda concurrency', async () => {
    const batchSize = __APP_CONFIG__.lambdaConcurrency > 0 ? __APP_CONFIG__.lambdaConcurrency : 5;
    const pending: Array<() => void> = [];
    mockDelete.mockImplementation(() => new Promise<void>((resolve) => { pending.push(() => resolve()); }));
    const { result } = renderHook(() => useBatchDelete());
    const items = Array.from({ length: batchSize + 1 }, (_, i) => ({ id: `uc-${i}`, name: `UC ${i}` }));

    let done!: Promise<unknown>;
    act(() => { done = result.current.deleteBatch(items); });
    expect(mockDelete).toHaveBeenCalledTimes(batchSize);

    await act(async () => {
      pending.splice(0).forEach((resolve) => resolve());
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(mockDelete).toHaveBeenCalledTimes(batchSize + 1);

    await act(async () => {
      pending.splice(0).forEach((resolve) => resolve());
      await done;
    });
  });

  it('sets deleting while the batch runs and resets it afterwards', async () => {
    let resolveDelete!: () => void;
    mockDelete.mockImplementation(() => new Promise<void>((resolve) => { resolveDelete = () => resolve(); }));
    const { result } = renderHook(() => useBatchDelete());

    expect(result.current.deleting).toBe(false);
    let done!: Promise<unknown>;
    act(() => { done = result.current.deleteBatch([{ id: 'uc-1', name: 'A' }]); });
    expect(result.current.deleting).toBe(true);

    await act(async () => {
      resolveDelete();
      await done;
    });
    expect(result.current.deleting).toBe(false);
  });
});

describe('delete flash helpers', () => {
  const ok = (id: string) => ({ usecaseId: id, usecaseName: `Name ${id}`, success: true });
  const bad = (id: string) => ({ usecaseId: id, usecaseName: `Name ${id}`, success: false, error: 'x' });

  it('describes the delete in progress', () => {
    expect(deleteInProgressFlash(3)).toEqual({
      type: 'info',
      content: 'Deleting 3 use case(s)...',
      loading: true,
    });
  });

  it('reports only success when every delete succeeded', () => {
    const onDismiss = vi.fn();
    const items = deleteResultFlashes([ok('1'), ok('2')], onDismiss);
    expect(items).toEqual([
      { type: 'success', content: 'Successfully deleted 2 use case(s)', dismissible: true, onDismiss },
    ]);
  });

  it('reports only the failures, by name, when every delete failed', () => {
    const onDismiss = vi.fn();
    const items = deleteResultFlashes([bad('1'), bad('2')], onDismiss);
    expect(items).toEqual([
      { type: 'error', content: 'Failed to delete 2 use case(s): Name 1, Name 2', dismissible: true, onDismiss },
    ]);
  });

  it('reports success first and failures second for a mixed result', () => {
    const onDismiss = vi.fn();
    const items = deleteResultFlashes([ok('1'), bad('2')], onDismiss);
    expect(items.map((i) => i.type)).toEqual(['success', 'error']);
    expect(items[0].content).toBe('Successfully deleted 1 use case(s)');
    expect(items[1].content).toBe('Failed to delete 1 use case(s): Name 2');
  });

  it('returns no items for an empty result', () => {
    expect(deleteResultFlashes([], vi.fn())).toEqual([]);
  });

  it('exposes the confirmation modal text', () => {
    expect(USECASE_DELETE_NOUN).toEqual({ singular: 'use case', plural: 'use cases', title: 'Use Cases' });
    expect(USECASE_DELETE_CONSEQUENCES).toBe(
      'This will remove all associated data including steps, executions, and configurations.',
    );
  });
});
