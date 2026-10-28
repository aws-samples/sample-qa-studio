import React, { useEffect, useState } from 'react';
import Table from '@cloudscape-design/components/table';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';
import Box from '@cloudscape-design/components/box';
import Select, { SelectProps } from '@cloudscape-design/components/select';
import { useTeamMembers } from '../../hooks/useTeamMembers';
import { usePermissions } from '../../auth';
import { Member, Role, TEAM_ROLES } from '../../types/permissions';
import AddMemberModal from './AddMemberModal';

interface MembersTabProps {
  teamId: string;
}

// 'admin' stays for display only: legacy team memberships may still carry it.
const ROLE_LABELS: Record<Role, string> = {
  admin: 'Admin',
  team_lead: 'Team Lead',
  editor: 'Editor',
  executor: 'Executor',
  viewer: 'Viewer',
};

/**
 * Roles the actor may assign on a team. Admin is studio-wide and is never
 * offered here (it is granted from Administration > Users).
 */
export function assignableTeamRoles(isAdmin: boolean, isTeamLead: boolean): Role[] {
  return isAdmin || isTeamLead ? [...TEAM_ROLES] : [];
}

const MembersTab: React.FC<MembersTabProps> = ({ teamId }) => {
  const { members, loading, fetchMembers, addMember, removeMember, changeRole } =
    useTeamMembers(teamId);
  const { isAdmin, isTeamLead } = usePermissions();
  const [showAddModal, setShowAddModal] = useState(false);

  useEffect(() => {
    fetchMembers();
  }, [fetchMembers]);

  // Determine which roles the actor can assign
  const getAllowedRoles = (): Role[] => assignableTeamRoles(isAdmin, isTeamLead);

  const canManageMembers = isAdmin || isTeamLead;

  const handleRoleChange = async (userId: string, newRole: Role) => {
    await changeRole(userId, newRole);
  };

  return (
    <SpaceBetween direction="vertical" size="l">
      <Table
        header={
          <Header
            variant="h2"
            actions={
              canManageMembers && (
                <Button
                  onClick={() => setShowAddModal(true)}
                  data-testid="add-member-button"
                >
                  Add Member
                </Button>
              )
            }
            counter={`(${members.length})`}
          >
            Members
          </Header>
        }
        columnDefinitions={[
          {
            id: 'userId',
            header: 'User',
            cell: (m: Member) => m.email || m.userId,
          },
          {
            id: 'role',
            header: 'Role',
            cell: (m: Member) => {
              if (!canManageMembers) {
                return ROLE_LABELS[m.role] || m.role;
              }
              const allowedRoles = getAllowedRoles();
              const roleOptions: SelectProps.Option[] = allowedRoles.map((r) => ({
                label: ROLE_LABELS[r],
                value: r,
              }));
              return (
                <Select
                  selectedOption={{ label: ROLE_LABELS[m.role], value: m.role }}
                  onChange={({ detail }) =>
                    handleRoleChange(m.userId, detail.selectedOption.value as Role)
                  }
                  options={roleOptions}
                  data-testid={`member-role-select-${m.userId}`}
                />
              );
            },
          },
          {
            id: 'joinedAt',
            header: 'Joined',
            cell: (m: Member) =>
              m.joinedAt ? new Date(m.joinedAt).toLocaleDateString() : '-',
          },
          {
            id: 'actions',
            header: 'Actions',
            cell: (m: Member) =>
              canManageMembers && (
                <Button
                  variant="link"
                  onClick={() => removeMember(m.userId)}
                  data-testid={`remove-member-${m.userId}`}
                >
                  Remove
                </Button>
              ),
          },
        ]}
        items={members}
        loading={loading}
        loadingText="Loading members..."
        empty={
          <Box textAlign="center" color="inherit">
            <b>No members</b>
            <Box variant="p" color="inherit">
              This team has no members yet.
            </Box>
            {canManageMembers && (
              <Button onClick={() => setShowAddModal(true)}>Add Member</Button>
            )}
          </Box>
        }
      />

      <AddMemberModal
        visible={showAddModal}
        onDismiss={() => setShowAddModal(false)}
        onSubmit={addMember}
        allowedRoles={getAllowedRoles()}
      />
    </SpaceBetween>
  );
};

export default MembersTab;
