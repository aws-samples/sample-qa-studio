import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { PermissionsContext, TeamRole } from './PermissionsContext';
import { derivePermissions } from './derivePermissions';

interface PermissionsProviderProps {
  children: React.ReactNode;
}

export function PermissionsProvider({ children }: PermissionsProviderProps) {
  const [scopes, setScopes] = useState<string[]>([]);
  const [teams, setTeams] = useState<TeamRole[]>([]);
  const [isAdmin, setIsAdmin] = useState(false);
  const [isTeamLead, setIsTeamLead] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const extractPermissions = async () => {
      try {
        const { fetchAuthSession } = await import('aws-amplify/auth');
        const session = await fetchAuthSession();

        if (session.tokens?.idToken) {
          const idTokenString = session.tokens.idToken.toString();
          const payload = JSON.parse(atob(idTokenString.split('.')[1]));

          // Extract scopes
          const scopeStr = payload.scope || '';
          const parsedScopes = scopeStr.split(' ').filter((s: string) => s.length > 0);
          setScopes(parsedScopes);

          // Extract groups and derive team context
          const groups: string[] = payload['cognito:groups'] || [];
          const derived = derivePermissions(groups, parsedScopes);
          setTeams(derived.teams);
          setIsAdmin(derived.isAdmin);
          setIsTeamLead(derived.isTeamLead);
        }
      } catch (error) {
        console.error('Failed to extract permissions:', error);
        setScopes([]);
        setTeams([]);
        setIsAdmin(false);
        setIsTeamLead(false);
      } finally {
        setIsLoading(false);
      }
    };

    extractPermissions();
  }, []);

  const hasScope = useCallback(
    (scope: string): boolean => {
      if (isAdmin || scopes.includes('api/admin')) {
        return true;
      }
      return scopes.includes(scope);
    },
    [scopes, isAdmin]
  );

  const value = useMemo(
    () => ({
      hasScope,
      isAdmin,
      isTeamLead,
      teams,
      isLoading,
      scopes,
    }),
    [hasScope, isAdmin, isTeamLead, teams, isLoading, scopes]
  );

  return (
    <PermissionsContext.Provider value={value}>
      {children}
    </PermissionsContext.Provider>
  );
}
