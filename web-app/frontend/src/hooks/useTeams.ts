import { useCallback } from 'react';
import { api } from '../utils/api';
import { useApiList } from './useApiList';
import { Team } from '../types/permissions';

export function useTeams() {
  const { items: teams, loading, error, reload: fetchTeams } = useApiList<Team>(
    'teams',
    'Failed to fetch teams',
  );

  const createTeam = useCallback(async (name: string): Promise<Team> => {
    const created = await api.post('teams', { name });
    await fetchTeams();
    return created;
  }, [fetchTeams]);

  const deleteTeam = useCallback(async (teamId: string): Promise<void> => {
    await api.delete(`teams/${encodeURIComponent(teamId)}`);
    await fetchTeams();
  }, [fetchTeams]);

  return { teams, loading, error, fetchTeams, createTeam, deleteTeam };
}
