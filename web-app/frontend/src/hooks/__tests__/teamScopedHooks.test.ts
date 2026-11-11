/**
 * The team-scoped admin hooks (members, shared access) and useUsers on top of
 * useApiList: they fetch on mount, skip the fetch without a team id, and
 * every mutation refreshes the list.
 */
import { renderHook, waitFor, act, cleanup } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

vi.mock('../../utils/api', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import { api } from '../../utils/api';
import { useTeamMembers } from '../useTeamMembers';
import { useSharedAccess } from '../useSharedAccess';
import { useUsers } from '../useUsers';

const mockGet = vi.mocked(api.get);

beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockResolvedValue([]);
});
afterEach(() => {
  cleanup();
});

describe('useTeamMembers', () => {
  it('fetches the members of the team on mount', async () => {
    mockGet.mockResolvedValue([{ userId: 'u1', role: 'editor' }]);
    const { result } = renderHook(() => useTeamMembers('team 1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mockGet).toHaveBeenCalledWith('teams/team%201/members');
    expect(result.current.members).toEqual([{ userId: 'u1', role: 'editor' }]);
  });

  it('does not fetch without a team id', () => {
    const { result } = renderHook(() => useTeamMembers(''));
    expect(mockGet).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
    expect(result.current.members).toEqual([]);
  });

  it('refreshes after add, change role and remove', async () => {
    const { result } = renderHook(() => useTeamMembers('t1'));
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.addMember('u1', 'editor');
      await result.current.changeRole('u1', 'team_lead');
      await result.current.removeMember('u1');
    });

    expect(api.post).toHaveBeenCalledWith('teams/t1/members', { userId: 'u1', role: 'editor' });
    expect(api.patch).toHaveBeenCalledWith('teams/t1/members/u1', { role: 'team_lead' });
    expect(api.delete).toHaveBeenCalledWith('teams/t1/members/u1');
    expect(mockGet).toHaveBeenCalledTimes(4);
  });

  it('reports a fetch failure with the hook-specific fallback', async () => {
    mockGet.mockRejectedValue({});
    const { result } = renderHook(() => useTeamMembers('t1'));
    await waitFor(() => expect(result.current.error).toBe('Failed to fetch members'));
  });
});

describe('useSharedAccess', () => {
  it('fetches the grants of the team on mount', async () => {
    mockGet.mockResolvedValue([{ id: 'g1' }]);
    const { result } = renderHook(() => useSharedAccess('t1'));
    await waitFor(() => expect(result.current.grants).toEqual([{ id: 'g1' }]));
    expect(mockGet).toHaveBeenCalledWith('teams/t1/shared-access');
  });

  it('does not fetch without a team id', () => {
    renderHook(() => useSharedAccess(''));
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('refreshes after grant and revoke', async () => {
    const { result } = renderHook(() => useSharedAccess('t1'));
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.grantAccess('t2', 'app-1', 'view');
      await result.current.revokeAccess('g 1');
    });

    expect(api.post).toHaveBeenCalledWith('teams/t1/shared-access', {
      targetTeamId: 't2',
      appId: 'app-1',
      level: 'view',
    });
    expect(api.delete).toHaveBeenCalledWith('teams/t1/shared-access/g%201');
    expect(mockGet).toHaveBeenCalledTimes(3);
  });

  it('reports a fetch failure with the hook-specific fallback', async () => {
    mockGet.mockRejectedValue({});
    const { result } = renderHook(() => useSharedAccess('t1'));
    await waitFor(() => expect(result.current.error).toBe('Failed to fetch shared access grants'));
  });
});

describe('useUsers', () => {
  it('fetches users on mount and refreshes after create, update and delete', async () => {
    mockGet.mockResolvedValue([{ id: 'u1' }]);
    const { result } = renderHook(() => useUsers());
    await waitFor(() => expect(result.current.users).toEqual([{ id: 'u1' }]));
    expect(mockGet).toHaveBeenCalledWith('users');

    await act(async () => {
      await result.current.createUser('a@example.com', 't1', 'editor');
      await result.current.updateUser('u1', { role: 'team_lead' });
      await result.current.deleteUser('u1');
    });

    expect(api.post).toHaveBeenCalledWith('users', { email: 'a@example.com', teamId: 't1', role: 'editor' });
    expect(api.patch).toHaveBeenCalledWith('users/u1', { role: 'team_lead' });
    expect(api.delete).toHaveBeenCalledWith('users/u1');
    expect(mockGet).toHaveBeenCalledTimes(4);
  });

  it('omits unset optional fields on create', async () => {
    const { result } = renderHook(() => useUsers());
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.createUser('a@example.com');
    });
    expect(api.post).toHaveBeenCalledWith('users', { email: 'a@example.com' });
  });

  it('reports a fetch failure with the hook-specific fallback', async () => {
    mockGet.mockRejectedValue({});
    const { result } = renderHook(() => useUsers());
    await waitFor(() => expect(result.current.error).toBe('Failed to fetch users'));
  });
});
