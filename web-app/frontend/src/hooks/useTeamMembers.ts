import { useState, useCallback } from 'react';
import { api } from '../utils/api';
import { Member, Role } from '../types/permissions';

export function useTeamMembers(teamId: string) {
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMembers = useCallback(async () => {
    if (!teamId) return;
    try {
      setLoading(true);
      setError(null);
      const data = await api.get(`teams/${encodeURIComponent(teamId)}/members`);
      setMembers(Array.isArray(data) ? data : []);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch members');
      setMembers([]);
    } finally {
      setLoading(false);
    }
  }, [teamId]);

  const addMember = useCallback(async (userId: string, role: Role): Promise<void> => {
    await api.post(`teams/${encodeURIComponent(teamId)}/members`, { userId, role });
    await fetchMembers();
  }, [teamId, fetchMembers]);

  const removeMember = useCallback(async (userId: string): Promise<void> => {
    await api.delete(`teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(userId)}`);
    await fetchMembers();
  }, [teamId, fetchMembers]);

  const changeRole = useCallback(async (userId: string, role: Role): Promise<void> => {
    await api.patch(`teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(userId)}`, { role });
    await fetchMembers();
  }, [teamId, fetchMembers]);

  return { members, loading, error, fetchMembers, addMember, removeMember, changeRole };
}
