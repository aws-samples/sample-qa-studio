import { renderHook, waitFor, act, cleanup } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

vi.mock('../../utils/api', () => ({
  api: { get: vi.fn() },
}));

import { api } from '../../utils/api';
import { useApiList } from '../useApiList';

const mockGet = vi.mocked(api.get);

/** A GET whose resolution the test controls. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  mockGet.mockReset();
});
afterEach(() => {
  cleanup();
});

describe('useApiList', () => {
  it('fetches the path on mount and exposes the items', async () => {
    mockGet.mockResolvedValue([{ id: 'a' }, { id: 'b' }]);
    const { result } = renderHook(() => useApiList<{ id: string }>('teams', 'fallback'));

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(mockGet).toHaveBeenCalledWith('teams');
    expect(result.current.items).toEqual([{ id: 'a' }, { id: 'b' }]);
    expect(result.current.error).toBeNull();
  });

  it('treats a non-array response as an empty list', async () => {
    mockGet.mockResolvedValue({ items: [1] });
    const { result } = renderHook(() => useApiList('teams', 'fallback'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items).toEqual([]);
  });

  it('sets the error message and clears the list on failure', async () => {
    mockGet.mockRejectedValue(new Error('Network failure'));
    const { result } = renderHook(() => useApiList('teams', 'fallback'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('Network failure');
    expect(result.current.items).toEqual([]);
  });

  it('falls back to the given message when the error has none', async () => {
    mockGet.mockRejectedValue({});
    const { result } = renderHook(() => useApiList('teams', 'Failed to fetch teams'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('Failed to fetch teams');
  });

  it('does not fetch for a null path', async () => {
    const { result } = renderHook(() => useApiList(null, 'fallback'));
    expect(result.current.loading).toBe(false);
    await act(async () => {
      await result.current.reload();
    });
    expect(mockGet).not.toHaveBeenCalled();
    expect(result.current.items).toEqual([]);
  });

  it('fetches once the path becomes known', async () => {
    mockGet.mockResolvedValue([{ id: 'm1' }]);
    const { result, rerender } = renderHook(({ path }) => useApiList(path, 'fallback'), {
      initialProps: { path: null as string | null },
    });
    expect(mockGet).not.toHaveBeenCalled();

    rerender({ path: 'teams/t1/members' });
    await waitFor(() => expect(result.current.items).toEqual([{ id: 'm1' }]));
    expect(mockGet).toHaveBeenCalledWith('teams/t1/members');
  });

  it('reload re-fetches and clears a previous error', async () => {
    mockGet.mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useApiList('teams', 'fallback'));
    await waitFor(() => expect(result.current.error).toBe('boom'));

    mockGet.mockResolvedValue([{ id: 'x' }]);
    await act(async () => {
      await result.current.reload();
    });

    expect(mockGet).toHaveBeenCalledTimes(2);
    expect(result.current.items).toEqual([{ id: 'x' }]);
    expect(result.current.error).toBeNull();
  });

  it('ignores an older response that resolves after a newer reload', async () => {
    const first = deferred<unknown>();
    const second = deferred<unknown>();
    mockGet.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);

    const { result } = renderHook(() => useApiList<string>('teams', 'fallback'));
    let reloading!: Promise<void>;
    act(() => {
      reloading = result.current.reload();
    });

    await act(async () => {
      second.resolve(['new']);
      await reloading;
    });
    expect(result.current.items).toEqual(['new']);
    expect(result.current.loading).toBe(false);

    await act(async () => {
      first.resolve(['old']);
      await first.promise;
    });
    expect(result.current.items).toEqual(['new']);
  });

  it('ignores an older failure that arrives after a newer success', async () => {
    const first = deferred<unknown>();
    mockGet.mockReturnValueOnce(first.promise).mockResolvedValueOnce(['new']);

    const { result } = renderHook(() => useApiList<string>('teams', 'fallback'));
    await act(async () => {
      await result.current.reload();
    });
    expect(result.current.items).toEqual(['new']);

    await act(async () => {
      first.reject(new Error('late'));
      await first.promise.catch(() => undefined);
    });
    expect(result.current.error).toBeNull();
    expect(result.current.items).toEqual(['new']);
  });

  it('ignores a response for a path that is no longer current', async () => {
    const teamOne = deferred<unknown>();
    mockGet.mockReturnValueOnce(teamOne.promise).mockResolvedValueOnce(['t2-member']);

    const { result, rerender } = renderHook(({ path }) => useApiList<string>(path, 'fallback'), {
      initialProps: { path: 'teams/t1/members' },
    });
    rerender({ path: 'teams/t2/members' });
    await waitFor(() => expect(result.current.items).toEqual(['t2-member']));

    await act(async () => {
      teamOne.resolve(['t1-member']);
      await teamOne.promise;
    });
    expect(result.current.items).toEqual(['t2-member']);
  });
});
