import { useCallback } from 'react';
import { api } from '../utils/api';
import { useApiList } from './useApiList';
import { SharedAccessGrant, AccessLevel } from '../types/permissions';

export function useSharedAccess(teamId: string) {
  const { items: grants, loading, error, reload: fetchGrants } = useApiList<SharedAccessGrant>(
    teamId ? `teams/${encodeURIComponent(teamId)}/shared-access` : null,
    'Failed to fetch shared access grants',
  );

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
