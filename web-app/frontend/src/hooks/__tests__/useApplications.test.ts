import { renderHook, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { useApplications } from '../useApplications';

vi.mock('../../utils/api', () => ({
  api: {
    get: vi.fn(),
  },
}));

import { api } from '../../utils/api';

const mockGet = vi.mocked(api.get);

describe('useApplications', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads applications and formats as select options', async () => {
    mockGet.mockResolvedValue([
      { id: 'app-1', name: 'My App', base_url: 'https://myapp.com' },
      { id: 'app-2', name: 'Other App', base_url: 'https://otherapp.com' },
    ]);

    const { result } = renderHook(() => useApplications());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.applications).toHaveLength(2);
    expect(result.current.options).toEqual([
      { label: 'My App', value: 'app-1', description: 'https://myapp.com' },
      { label: 'Other App', value: 'app-2', description: 'https://otherapp.com' },
    ]);
    expect(mockGet).toHaveBeenCalledWith('applications');
  });

  it('returns empty options when no applications', async () => {
    mockGet.mockResolvedValue([]);

    const { result } = renderHook(() => useApplications());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.applications).toEqual([]);
    expect(result.current.options).toEqual([]);
  });

  it('returns empty array gracefully on API error', async () => {
    mockGet.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useApplications());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.applications).toEqual([]);
    expect(result.current.options).toEqual([]);
  });

  it('loading is true initially and false after load', async () => {
    let resolveGet: (value: unknown) => void;
    mockGet.mockImplementation(() => new Promise((resolve) => { resolveGet = resolve; }));

    const { result } = renderHook(() => useApplications());

    expect(result.current.loading).toBe(true);

    resolveGet!([{ id: 'app-1', name: 'App', base_url: 'https://app.com' }]);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.applications).toHaveLength(1);
  });
});
