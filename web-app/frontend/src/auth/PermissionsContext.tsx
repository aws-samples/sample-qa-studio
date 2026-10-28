import { createContext } from 'react';

export interface TeamRole {
  team_id: string;
  role: string;
  group_name: string;
}

export interface PermissionsContextValue {
  /** Check if user has the given scope (with admin inheritance) */
  hasScope: (scope: string) => boolean;
  /** Whether the user is an admin */
  isAdmin: boolean;
  /** Whether the user is a team lead of any team */
  isTeamLead: boolean;
  /** List of team memberships */
  teams: TeamRole[];
  /** Whether permissions are still loading */
  isLoading: boolean;
  /** All resolved scopes */
  scopes: string[];
}

export const PermissionsContext = createContext<PermissionsContextValue>({
  hasScope: () => false,
  isAdmin: false,
  isTeamLead: false,
  teams: [],
  isLoading: true,
  scopes: [],
});
