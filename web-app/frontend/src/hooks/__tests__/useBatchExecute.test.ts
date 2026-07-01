import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { useBatchExecute } from '../useBatchExecute';

vi.mock('../../utils/api', () => ({
  api: {
    post: vi.fn(),
  },
}));

import { api } from '../../utils/api';

const mockPost = vi.mocked(api.post);

describe('useBatchExecute', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('executes batch of usecases and returns results with success/failure per item', async () => {
    mockPost.mockResolvedValue({});

    const { result } = renderHook(() => useBatchExecute());

    let batchResults: any;
    await act(async () => {
      batchResults = await result.current.executeBatch([
        { id: 'uc-1', name: 'Login Test' },
        { id: 'uc-2', name: 'Checkout Test' },
      ]);
    });

    expect(batchResults).toHaveLength(2);
    expect(batchResults[0]).toEqual({ usecaseId: 'uc-1', usecaseName: 'Login Test', success: true });
    expect(batchResults[1]).toEqual({ usecaseId: 'uc-2', usecaseName: 'Checkout Test', success: true });
    expect(mockPost).toHaveBeenCalledTimes(2);
    expect(mockPost).toHaveBeenCalledWith('usecase/uc-1/execute?trigger-type=OnDemandHeadless', {});
    expect(mockPost).toHaveBeenCalledWith('usecase/uc-2/execute?trigger-type=OnDemandHeadless', {});
  });

  it('returns correct successCount and failureCount', async () => {
    mockPost
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce(new Error('Timeout'));

    const { result } = renderHook(() => useBatchExecute());

    await act(async () => {
      await result.current.executeBatch([
        { id: 'uc-1', name: 'Login Test' },
        { id: 'uc-2', name: 'Checkout Test' },
      ]);
    });

    expect(result.current.successCount).toBe(1);
    expect(result.current.failureCount).toBe(1);
  });

  it('handles individual usecase failure while others succeed — partial results returned', async () => {
    mockPost
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce(new Error('Server error'))
      .mockResolvedValueOnce({});

    const { result } = renderHook(() => useBatchExecute());

    let batchResults: any;
    await act(async () => {
      batchResults = await result.current.executeBatch([
        { id: 'uc-1', name: 'Test A' },
        { id: 'uc-2', name: 'Test B' },
        { id: 'uc-3', name: 'Test C' },
      ]);
    });

    expect(batchResults).toHaveLength(3);
    expect(batchResults[0].success).toBe(true);
    expect(batchResults[1].success).toBe(false);
    expect(batchResults[1].error).toBe('Server error');
    expect(batchResults[2].success).toBe(true);
    expect(result.current.successCount).toBe(2);
    expect(result.current.failureCount).toBe(1);
  });

  it('marks all as failed when all usecases fail', async () => {
    mockPost.mockRejectedValue(new Error('Service unavailable'));

    const { result } = renderHook(() => useBatchExecute());

    let batchResults: any;
    await act(async () => {
      batchResults = await result.current.executeBatch([
        { id: 'uc-1', name: 'Test A' },
        { id: 'uc-2', name: 'Test B' },
      ]);
    });

    expect(batchResults).toHaveLength(2);
    expect(batchResults.every((r: any) => r.success === false)).toBe(true);
    expect(batchResults.every((r: any) => r.error === 'Service unavailable')).toBe(true);
    expect(result.current.successCount).toBe(0);
    expect(result.current.failureCount).toBe(2);
  });

  it('sets executing to true during execution and false after', async () => {
    let resolvePost: (value: unknown) => void;
    mockPost.mockImplementation(() => new Promise((resolve) => { resolvePost = resolve; }));

    const { result } = renderHook(() => useBatchExecute());

    expect(result.current.executing).toBe(false);

    let executionPromise: Promise<any>;
    act(() => {
      executionPromise = result.current.executeBatch([{ id: 'uc-1', name: 'Test' }]);
    });

    // executing should be true while awaiting
    expect(result.current.executing).toBe(true);

    await act(async () => {
      resolvePost!({});
      await executionPromise;
    });

    expect(result.current.executing).toBe(false);
  });
});
