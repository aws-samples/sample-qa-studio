import { useCallback } from 'react';
import { api } from '../utils/api';
import { useApiList } from './useApiList';
import { UserWithTeams, Role } from '../types/permissions';

export function useUsers() {
  const { items: users, loading, error, reload: fetchUsers } = useApiList<UserWithTeams>(
    'users',
    'Failed to fetch users',
  );

  const createUser = useCallback(async (
    email: string,
    teamId?: string,
    role?: Role
  ): Promise<void> => {
    const body: Record<string, any> = { email };
    if (teamId) body.teamId = teamId;
    if (role) body.role = role;
    await api.post('users', body);
    await fetchUsers();
  }, [fetchUsers]);

  const updateUser = useCallback(async (
    userId: string,
    updates: { teamId?: string; role?: Role }
  ): Promise<void> => {
    await api.patch(`users/${encodeURIComponent(userId)}`, updates);
    await fetchUsers();
  }, [fetchUsers]);

  const deleteUser = useCallback(async (userId: string): Promise<void> => {
    await api.delete(`users/${encodeURIComponent(userId)}`);
    await fetchUsers();
  }, [fetchUsers]);

  return { users, loading, error, fetchUsers, createUser, updateUser, deleteUser };
}
