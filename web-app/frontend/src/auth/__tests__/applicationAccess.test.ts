import { describe, it, expect } from 'vitest';
import { canCreateApplication, canManageApplication, teamLeadTeamIds } from '../applicationAccess';
import type { TeamRole } from '../PermissionsContext';

const role = (team_id: string, r: string): TeamRole => ({ team_id, role: r, group_name: `team-${team_id}-${r}` });

describe('applicationAccess', () => {
  it('lists only team-lead teams', () => {
    expect(teamLeadTeamIds([role('a', 'team_lead'), role('b', 'editor')])).toEqual(['a']);
  });

  it('create: admin or team lead only', () => {
    expect(canCreateApplication(true, [])).toBe(true);
    expect(canCreateApplication(false, [role('a', 'team_lead')])).toBe(true);
    expect(canCreateApplication(false, [role('a', 'editor')])).toBe(false);
    expect(canCreateApplication(false, [])).toBe(false);
  });

  it('manage: admin or team lead of the owning team', () => {
    expect(canManageApplication(true, [], null)).toBe(true);
    expect(canManageApplication(false, [role('a', 'team_lead')], 'a')).toBe(true);
    expect(canManageApplication(false, [role('a', 'editor')], 'a')).toBe(false);
    expect(canManageApplication(false, [role('b', 'team_lead')], 'a')).toBe(false);
  });

  it('manage: orphaned app is admin-only', () => {
    expect(canManageApplication(false, [role('a', 'team_lead')], null)).toBe(false);
    expect(canManageApplication(false, [role('a', 'team_lead')], undefined)).toBe(false);
  });
});
