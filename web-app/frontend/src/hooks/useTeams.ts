import { useState, useEffect, useCallback } from 'react';
import { api } from '../utils/api';
import { Team } from '../types/permissions';

export function useTeams() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTeams = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.get('teams');
      setTeams(Array.isArray(data) ? data : []);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch teams');
      setTeams([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTeams();
  }, [fetchTeams]);

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
