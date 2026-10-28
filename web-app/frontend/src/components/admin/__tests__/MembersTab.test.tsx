import React from 'react';
import { render } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import MembersTab, { assignableTeamRoles } from '../MembersTab';

vi.mock('../../../hooks/useTeamMembers', () => ({
  useTeamMembers: () => ({
    members: [],
    loading: false,
    fetchMembers: vi.fn(),
    addMember: vi.fn(),
    removeMember: vi.fn(),
    changeRole: vi.fn(),
  }),
}));

const mockUsePermissions = vi.fn();
vi.mock('../../../auth', () => ({
  usePermissions: () => mockUsePermissions(),
}));

// Capture the roles MembersTab offers in the Add Member modal.
let addModalRoles: string[] | undefined;
vi.mock('../AddMemberModal', () => ({
  default: (props: { allowedRoles: string[] }) => {
    addModalRoles = props.allowedRoles;
    return null;
  },
}));

describe('assignableTeamRoles', () => {
  it('admin is offered team roles only, never admin', () => {
    expect(assignableTeamRoles(true, false)).toEqual(['team_lead', 'editor', 'executor', 'viewer']);
  });

  it('team lead is offered team roles only', () => {
    expect(assignableTeamRoles(false, true)).toEqual(['team_lead', 'editor', 'executor', 'viewer']);
  });

  it('other users are offered nothing', () => {
    expect(assignableTeamRoles(false, false)).toEqual([]);
  });
});

describe('MembersTab', () => {
  beforeEach(() => {
    addModalRoles = undefined;
  });

  it('does not offer admin to an admin in the Add Member modal', () => {
    mockUsePermissions.mockReturnValue({ isAdmin: true, isTeamLead: false });
    render(<MembersTab teamId="team-1" />);
    expect(addModalRoles).toEqual(['team_lead', 'editor', 'executor', 'viewer']);
    expect(addModalRoles).not.toContain('admin');
  });

  it('does not offer admin to a team lead in the Add Member modal', () => {
    mockUsePermissions.mockReturnValue({ isAdmin: false, isTeamLead: true });
    render(<MembersTab teamId="team-1" />);
    expect(addModalRoles).not.toContain('admin');
  });
});
