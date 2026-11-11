import { useCallback } from 'react';
import { api } from '../utils/api';
import { useApiList } from './useApiList';
import { Member, Role } from '../types/permissions';

export function useTeamMembers(teamId: string) {
  const { items: members, loading, error, reload: fetchMembers } = useApiList<Member>(
    teamId ? `teams/${encodeURIComponent(teamId)}/members` : null,
    'Failed to fetch members',
  );

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
