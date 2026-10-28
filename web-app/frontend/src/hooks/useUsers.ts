import { useState, useEffect, useCallback } from 'react';
import { api } from '../utils/api';
import { UserWithTeams, Role } from '../types/permissions';

export function useUsers() {
  const [users, setUsers] = useState<UserWithTeams[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchUsers = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.get('users');
      setUsers(Array.isArray(data) ? data : []);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch users');
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

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
