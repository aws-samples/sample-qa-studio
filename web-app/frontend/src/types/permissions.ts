/**
 * Types for team-based permissions and user management.
 */

export type AccessLevel = 'view' | 'execute' | 'full';

export type Role = 'admin' | 'team_lead' | 'editor' | 'executor' | 'viewer';

/**
 * Roles that can be held inside a team. Admin is studio-wide (global `admins`
 * group) and is never a team role. Mirrors TEAM_ROLES in role_scopes.py.
 */
export const TEAM_ROLES = ['team_lead', 'editor', 'executor', 'viewer'] as const;

export type TeamRoleName = (typeof TEAM_ROLES)[number];

/**
 * OAuth (M2M) clients are bound to one team and may never hold these scopes.
 * Mirrors M2M_FORBIDDEN_SCOPES in role_scopes.py.
 */
export const M2M_FORBIDDEN_SCOPES: readonly string[] = ['api/admin', 'api/teams.manage'];

/** Team roles allowed to create OAuth clients for a team (editor or higher). */
export const OAUTH_CLIENT_CREATOR_ROLES = ['team_lead', 'editor'] as const;

export interface Team {
  id: string;
  name: string;
  description?: string;
  memberCount: number;
  applicationCount: number;
  created_by?: string;
  created_at?: string;
}

export interface Member {
  userId: string;
  email?: string;
  role: Role;
  joinedAt: string;
}

export interface SharedAccessGrant {
  grantId: string;
  targetTeamId: string;
  targetTeamName: string;
  appId?: string;
  accessLevel: AccessLevel;
  grantedAt: string;
}

export interface UserWithTeams {
  userId: string;
  email: string;
  teams: Array<{ teamId: string; name: string; role: Role }>;
  isAdmin?: boolean;
}
