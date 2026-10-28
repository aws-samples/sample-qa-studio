import type { TeamRole } from './PermissionsContext';

/**
 * Application metadata rules (mirror the backend H-3 checks):
 * - create: studio admin, or Team Lead of the target team;
 * - edit / delete: studio admin, or Team Lead of the owning team.
 * Shared access never allows changing an application's metadata.
 */

/** Ids of the teams where the user is a Team Lead. */
export function teamLeadTeamIds(teams: TeamRole[]): string[] {
  return teams.filter((t) => t.role === 'team_lead').map((t) => t.team_id);
}

/** Whether the user may create an application for at least one team. */
export function canCreateApplication(isAdmin: boolean, teams: TeamRole[]): boolean {
  return isAdmin || teamLeadTeamIds(teams).length > 0;
}

/** Whether the user may edit or delete an application owned by `ownerTeamId`. */
export function canManageApplication(
  isAdmin: boolean,
  teams: TeamRole[],
  ownerTeamId: string | null | undefined,
): boolean {
  if (isAdmin) return true;
  return !!ownerTeamId && teamLeadTeamIds(teams).includes(ownerTeamId);
}
