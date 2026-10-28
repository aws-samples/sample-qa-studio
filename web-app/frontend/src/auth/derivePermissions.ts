import { TEAM_ROLES } from '../types/permissions';
import type { TeamRole } from './PermissionsContext';

/**
 * Team group naming regex: team-{teamId}-{role}
 * Matches the backend role_scopes.py parse_group pattern.
 */
const TEAM_GROUP_RE = /^team-([a-zA-Z0-9_-]+)-([a-z_]+)$/;

/** The only group that grants studio-wide admin (mirrors role_scopes.is_admin_group). */
const ADMINS_GROUP = 'admins';

const TEAM_ROLE_SET: ReadonlySet<string> = new Set(TEAM_ROLES);

export interface DerivedPermissions {
  teams: TeamRole[];
  isAdmin: boolean;
  isTeamLead: boolean;
}

/**
 * Derive team memberships and admin status from Cognito groups and token scopes.
 *
 * - isAdmin comes only from the global `admins` group or the `api/admin` scope.
 *   A `team-{id}-admin` group is not a team role and grants nothing.
 * - teams contains only groups whose role is in TEAM_ROLES.
 * - isTeamLead means `team_lead` in at least one team.
 */
export function derivePermissions(groups: string[], scopes: string[]): DerivedPermissions {
  const teams: TeamRole[] = [];
  let isAdmin = scopes.includes('api/admin');

  for (const group of groups) {
    const trimmed = group.trim();
    if (trimmed === ADMINS_GROUP) {
      isAdmin = true;
      continue;
    }
    const match = TEAM_GROUP_RE.exec(trimmed);
    if (match && TEAM_ROLE_SET.has(match[2])) {
      teams.push({ team_id: match[1], role: match[2], group_name: trimmed });
    }
  }

  const isTeamLead = teams.some((t) => t.role === 'team_lead');
  return { teams, isAdmin, isTeamLead };
}
