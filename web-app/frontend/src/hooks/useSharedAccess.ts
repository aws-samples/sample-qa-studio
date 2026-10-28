import { useState, useCallback } from 'react';
import { api } from '../utils/api';
import { SharedAccessGrant, AccessLevel } from '../types/permissions';

export function useSharedAccess(teamId: string) {
  const [grants, setGrants] = useState<SharedAccessGrant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchGrants = useCallback(async () => {
    if (!teamId) return;
    try {
      setLoading(true);
      setError(null);
      const data = await api.get(`teams/${encodeURIComponent(teamId)}/shared-access`);
      setGrants(Array.isArray(data) ? data : []);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch shared access grants');
      setGrants([]);
    } finally {
      setLoading(false);
    }
  }, [teamId]);

  const grantAccess = useCallback(async (
    targetTeamId: string,
    appId: string,
    level: AccessLevel
  ): Promise<void> => {
    await api.post(`teams/${encodeURIComponent(teamId)}/shared-access`, {
      targetTeamId,
      appId,
      level,
    });
    await fetchGrants();
  }, [teamId, fetchGrants]);

  const revokeAccess = useCallback(async (grantId: string): Promise<void> => {
    await api.delete(`teams/${encodeURIComponent(teamId)}/shared-access/${encodeURIComponent(grantId)}`);
    await fetchGrants();
  }, [teamId, fetchGrants]);

  return { grants, loading, error, fetchGrants, grantAccess, revokeAccess };
}
