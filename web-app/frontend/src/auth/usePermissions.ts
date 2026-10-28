import { useContext } from 'react';
import { PermissionsContext, PermissionsContextValue } from './PermissionsContext';

/**
 * Hook to access the current user's permissions.
 *
 * Returns:
 * - hasScope(scope): Check if user has the given scope (with admin inheritance)
 * - isAdmin: Whether the user has admin privileges
 * - isTeamLead: Whether the user is a team lead of any team
 * - teams: List of team memberships with roles
 * - isLoading: Whether permissions are still being resolved
 * - scopes: Full list of resolved scopes
 */
export function usePermissions(): PermissionsContextValue {
  return useContext(PermissionsContext);
}
