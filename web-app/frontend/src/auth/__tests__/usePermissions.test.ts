/**
 * Tests for permission derivation (derivePermissions) and the PermissionsProvider.
 *
 * derivePermissions mirrors the backend role_scopes.py rules: admin comes only
 * from the global `admins` group (or the api/admin scope), and team groups are
 * recognized only for TEAM_ROLES.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { derivePermissions } from '../derivePermissions';
import { PermissionsProvider } from '../PermissionsProvider';
import { usePermissions } from '../usePermissions';
import type { PermissionsContextValue } from '../PermissionsContext';
import { TEAM_ROLES } from '../../types/permissions';

const mockFetchAuthSession = vi.fn();
vi.mock('aws-amplify/auth', () => ({
  fetchAuthSession: () => mockFetchAuthSession(),
}));

describe('derivePermissions', () => {
  describe('admin user', () => {
    it('recognizes admins group as admin', () => {
      expect(derivePermissions(['admins'], []).isAdmin).toBe(true);
    });

    it('recognizes the api/admin scope as admin', () => {
      expect(derivePermissions([], ['api/admin']).isAdmin).toBe(true);
    });

    it('admin has no team roles from the admins group', () => {
      expect(derivePermissions(['admins'], ['api/admin']).teams).toHaveLength(0);
    });
  });

  describe('team-scoped admin group (C-1)', () => {
    it('team-x-admin does not mean isAdmin', () => {
      const result = derivePermissions(['team-x-admin'], []);
      expect(result.isAdmin).toBe(false);
      expect(result.isTeamLead).toBe(false);
      expect(result.teams).toHaveLength(0);
    });

    it('team-x-admin next to a team_lead group only yields team lead', () => {
      const result = derivePermissions(['team-x-team_lead', 'team-x-admin'], ['api/teams.manage']);
      expect(result.isAdmin).toBe(false);
      expect(result.isTeamLead).toBe(true);
      expect(result.teams).toEqual([
        { team_id: 'x', role: 'team_lead', group_name: 'team-x-team_lead' },
      ]);
    });
  });

  describe('team roles', () => {
    it.each(TEAM_ROLES)('parses team-alpha-%s', (role) => {
      const result = derivePermissions([`team-alpha-${role}`], []);
      expect(result.teams).toEqual([
        { team_id: 'alpha', role, group_name: `team-alpha-${role}` },
      ]);
      expect(result.isAdmin).toBe(false);
      expect(result.isTeamLead).toBe(role === 'team_lead');
    });

    it('handles multiple team groups', () => {
      const result = derivePermissions(
        ['team-alpha-editor', 'team-beta-viewer', 'team-gamma-team_lead'],
        ['api/usecases.read']
      );
      expect(result.teams.map((t) => t.team_id)).toEqual(['alpha', 'beta', 'gamma']);
      expect(result.isTeamLead).toBe(true);
    });
  });

  describe('legacy and unknown groups', () => {
    it('users group does not create team roles', () => {
      const result = derivePermissions(['users'], ['api/usecases.read']);
      expect(result.teams).toHaveLength(0);
      expect(result.isAdmin).toBe(false);
    });

    it('ignores unknown groups', () => {
      const result = derivePermissions(['random-group'], []);
      expect(result).toEqual({ teams: [], isAdmin: false, isTeamLead: false });
    });

    it('ignores team groups with invalid roles', () => {
      expect(derivePermissions(['team-abc-superuser'], []).teams).toHaveLength(0);
    });

    it('ignores malformed team group names', () => {
      expect(derivePermissions(['team--editor', 'teamabc-editor'], []).teams).toHaveLength(0);
    });

    it('handles empty groups gracefully', () => {
      expect(derivePermissions([], [])).toEqual({ teams: [], isAdmin: false, isTeamLead: false });
    });
  });
});

function fakeIdToken(payload: Record<string, unknown>): string {
  return `header.${btoa(JSON.stringify(payload))}.signature`;
}

async function renderProvider(payload: Record<string, unknown>): Promise<PermissionsContextValue> {
  mockFetchAuthSession.mockResolvedValue({
    tokens: { idToken: { toString: () => fakeIdToken(payload) } },
  });
  let captured: PermissionsContextValue | undefined;
  function Probe() {
    captured = usePermissions();
    return null;
  }
  render(React.createElement(PermissionsProvider, null, React.createElement(Probe)));
  await waitFor(() => expect(captured?.isLoading).toBe(false));
  return captured as PermissionsContextValue;
}

describe('PermissionsProvider', () => {
  beforeEach(() => {
    mockFetchAuthSession.mockReset();
  });

  it('team-x-admin member is not admin and gets no extra scopes', async () => {
    const perms = await renderProvider({
      'cognito:groups': ['team-x-admin'],
      scope: 'api/usecases.read',
    });
    expect(perms.isAdmin).toBe(false);
    expect(perms.isTeamLead).toBe(false);
    expect(perms.hasScope('api/admin')).toBe(false);
    expect(perms.hasScope('api/usecases.read')).toBe(true);
  });

  it('admins group member is admin and passes every scope check', async () => {
    const perms = await renderProvider({ 'cognito:groups': ['admins'], scope: 'api/admin' });
    expect(perms.isAdmin).toBe(true);
    expect(perms.hasScope('api/teams.manage')).toBe(true);
    expect(perms.hasScope('api/nonexistent')).toBe(true);
  });

  it('team lead is team lead but not admin', async () => {
    const perms = await renderProvider({
      'cognito:groups': ['team-beta-team_lead'],
      scope: 'api/teams.manage',
    });
    expect(perms.isTeamLead).toBe(true);
    expect(perms.isAdmin).toBe(false);
    expect(perms.teams[0].role).toBe('team_lead');
  });

  it('falls back to no permissions when the session cannot be read', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    mockFetchAuthSession.mockRejectedValue(new Error('no session'));
    let captured: PermissionsContextValue | undefined;
    function Probe() {
      captured = usePermissions();
      return null;
    }
    render(React.createElement(PermissionsProvider, null, React.createElement(Probe)));
    await waitFor(() => expect(captured?.isLoading).toBe(false));
    expect(captured?.isAdmin).toBe(false);
    expect(captured?.teams).toEqual([]);
    errorSpy.mockRestore();
  });
});
