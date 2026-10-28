import { renderHook, waitFor, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { useTeams } from '../useTeams';

vi.mock('../../utils/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import { api } from '../../utils/api';

const mockGet = vi.mocked(api.get);
const mockPost = vi.mocked(api.post);
const mockDelete = vi.mocked(api.delete);

describe('useTeams', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches teams on mount and returns them', async () => {
    mockGet.mockResolvedValue([
      { id: 'team-1', name: 'Alpha', memberCount: 3, applicationCount: 2 },
      { id: 'team-2', name: 'Beta', memberCount: 1, applicationCount: 0 },
    ]);

    const { result } = renderHook(() => useTeams());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.teams).toHaveLength(2);
    expect(result.current.teams[0].name).toBe('Alpha');
    expect(mockGet).toHaveBeenCalledWith('teams');
  });

  it('handles API errors gracefully', async () => {
    mockGet.mockRejectedValue(new Error('Network failure'));

    const { result } = renderHook(() => useTeams());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.teams).toEqual([]);
    expect(result.current.error).toBe('Network failure');
  });

  it('createTeam calls POST and refreshes list', async () => {
    mockGet.mockResolvedValue([]);
    mockPost.mockResolvedValue({ id: 'team-new', name: 'New Team', memberCount: 0, applicationCount: 0 });

    const { result } = renderHook(() => useTeams());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Update mockGet to return the new team on refresh
    mockGet.mockResolvedValue([{ id: 'team-new', name: 'New Team', memberCount: 0, applicationCount: 0 }]);

    await act(async () => {
      await result.current.createTeam('New Team');
    });

    expect(mockPost).toHaveBeenCalledWith('teams', { name: 'New Team' });
    // fetchTeams was called again
    expect(mockGet).toHaveBeenCalledTimes(2);
  });

  it('deleteTeam calls DELETE and refreshes list', async () => {
    mockGet.mockResolvedValue([
      { id: 'team-1', name: 'Alpha', memberCount: 0, applicationCount: 0 },
    ]);
    mockDelete.mockResolvedValue(null);

    const { result } = renderHook(() => useTeams());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    mockGet.mockResolvedValue([]);

    await act(async () => {
      await result.current.deleteTeam('team-1');
    });

    expect(mockDelete).toHaveBeenCalledWith('teams/team-1');
    expect(mockGet).toHaveBeenCalledTimes(2);
  });

  it('loading is true initially and false after fetch', async () => {
    let resolveGet: (value: unknown) => void;
    mockGet.mockImplementation(() => new Promise((resolve) => { resolveGet = resolve; }));

    const { result } = renderHook(() => useTeams());

    expect(result.current.loading).toBe(true);

    await act(async () => {
      resolveGet!([]);
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
  });
});
