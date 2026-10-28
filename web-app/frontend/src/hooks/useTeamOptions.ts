import { useEffect, useState } from 'react';
import type { SelectProps } from '@cloudscape-design/components/select';
import { api } from '../utils/api';
import { usePermissions } from '../auth';

/**
 * Team options for a "Team" select.
 *
 * Admins get every team. Other users get the teams where they hold one of
 * `eligibleRoles` (names are fetched per team). Loads only while `enabled`.
 */
export function useTeamOptions(enabled: boolean, eligibleRoles: readonly string[]): SelectProps.Option[] {
  const { isAdmin, teams } = usePermissions();
  const [options, setOptions] = useState<SelectProps.Option[]>([]);
  const eligibleIds = teams.filter((t) => eligibleRoles.includes(t.role)).map((t) => t.team_id);
  const eligibleKey = eligibleIds.join(',');

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const apply = (opts: SelectProps.Option[]) => { if (!cancelled) setOptions(opts); };
    if (isAdmin) {
      api.get('teams')
        .then((data: any) => {
          const all = data?.teams || data || [];
          apply(all.map((t: any) => ({ label: t.name, value: t.id })));
        })
        .catch(() => apply([]));
    } else {
      Promise.all(
        eligibleIds.map((id) => api.get(`teams/${encodeURIComponent(id)}`).catch(() => null)),
      ).then((results) => {
        apply(results.filter(Boolean).map((t: any) => ({ label: t.name, value: t.id })));
      });
    }
    return () => { cancelled = true; };
    // eligibleKey captures eligibleIds by value
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, isAdmin, eligibleKey]);

  return options;
}
