import React, { useState } from 'react';
import Table from '@cloudscape-design/components/table';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';
import Box from '@cloudscape-design/components/box';
import TextFilter from '@cloudscape-design/components/text-filter';
import Pagination from '@cloudscape-design/components/pagination';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Badge from '@cloudscape-design/components/badge';
import Select, { SelectProps } from '@cloudscape-design/components/select';
import Alert from '@cloudscape-design/components/alert';
import { useUsers } from '../../hooks/useUsers';
import { useTeams } from '../../hooks/useTeams';
import { UserWithTeams } from '../../types/permissions';
import CreateUserModal from './CreateUserModal';
import EditUserModal from './EditUserModal';

const PAGE_SIZE = 10;

const UsersListPage: React.FC = () => {
  const { users, loading, error, createUser, updateUser } = useUsers();
  const { teams } = useTeams();

  const [filterText, setFilterText] = useState('');
  const [teamFilter, setTeamFilter] = useState<SelectProps.Option>({ label: 'All teams', value: '' });
  const [roleFilter, setRoleFilter] = useState<SelectProps.Option>({ label: 'All roles', value: '' });
  const [currentPage, setCurrentPage] = useState(1);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingUser, setEditingUser] = useState<UserWithTeams | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const teamFilterOptions: SelectProps.Option[] = [
    { label: 'All teams', value: '' },
    { label: 'Administrators', value: '__admin__' },
    { label: 'Unassigned', value: '__unassigned__' },
    ...teams.map((t) => ({ label: t.name, value: t.id })),
  ];
  const roleFilterOptions: SelectProps.Option[] = [
    { label: 'All roles', value: '' },
    { label: 'Admin', value: 'admin' },
    { label: 'Team Lead', value: 'team_lead' },
    { label: 'Editor', value: 'editor' },
    { label: 'Executor', value: 'executor' },
    { label: 'Viewer', value: 'viewer' },
  ];

  const filteredUsers = users.filter((u) => {
    if (filterText && !u.email.toLowerCase().includes(filterText.toLowerCase())) return false;

    const tf = teamFilter.value;
    if (tf === '__admin__' && !u.isAdmin) return false;
    if (tf === '__unassigned__' && (u.isAdmin || (u.teams && u.teams.length > 0))) return false;
    if (tf && tf !== '__admin__' && tf !== '__unassigned__' &&
        !(u.teams || []).some((t) => t.teamId === tf)) return false;

    const rf = roleFilter.value;
    if (rf === 'admin' && !u.isAdmin) return false;
    if (rf && rf !== 'admin' && !(u.teams || []).some((t) => t.role === rf)) return false;

    return true;
  });

  const totalPages = Math.ceil(filteredUsers.length / PAGE_SIZE);
  const paginatedUsers = filteredUsers.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE
  );

  const handleCreateUser = async (email: string, teamId?: string, role?: any) => {
    await createUser(email, teamId, role);
    setSuccessMessage(`User "${email}" created successfully`);
    setTimeout(() => setSuccessMessage(null), 5000);
  };

  return (
    <SpaceBetween direction="vertical" size="l">
      {successMessage && (
        <Alert type="success" dismissible onDismiss={() => setSuccessMessage(null)}>
          {successMessage}
        </Alert>
      )}

      <Table
        header={
          <Header
            variant="h1"
            actions={
              <Button
                variant="primary"
                onClick={() => setShowCreateModal(true)}
                data-testid="create-user-button"
              >
                Create User
              </Button>
            }
            counter={`(${filteredUsers.length})`}
          >
            Users
          </Header>
        }
        columnDefinitions={[
          {
            id: 'email',
            header: 'Email',
            cell: (u: UserWithTeams) => u.email,
            sortingField: 'email',
          },
          {
            id: 'team',
            header: 'Team',
            cell: (u: UserWithTeams) => {
              if (u.isAdmin) {
                return <Badge color="grey">Studio-wide</Badge>;
              }
              if (!u.teams || u.teams.length === 0) {
                return (
                  <StatusIndicator type="warning" data-testid={`unassigned-${u.userId}`}>
                    Unassigned
                  </StatusIndicator>
                );
              }
              return u.teams.map((t) => t.name).join(', ');
            },
          },
          {
            id: 'role',
            header: 'Role',
            cell: (u: UserWithTeams) => {
              if (u.isAdmin) {
                return <Badge color="blue">Administrator</Badge>;
              }
              if (!u.teams || u.teams.length === 0) return '-';
              return u.teams.map((t) => t.role).join(', ');
            },
          },
          {
            id: 'actions',
            header: 'Actions',
            cell: (u: UserWithTeams) => (
              <Button
                variant="link"
                onClick={() => {
                  setEditingUser(u);
                  setShowEditModal(true);
                }}
                data-testid={`user-actions-${u.userId}`}
              >
                Edit
              </Button>
            ),
          },
        ]}
        items={paginatedUsers}
        loading={loading}
        loadingText="Loading users..."
        filter={
          <SpaceBetween direction="horizontal" size="xs">
            <div style={{ minWidth: 280 }}>
              <TextFilter
                filteringText={filterText}
                onChange={({ detail }) => {
                  setFilterText(detail.filteringText);
                  setCurrentPage(1);
                }}
                filteringPlaceholder="Find users by email"
                data-testid="users-filter"
              />
            </div>
            <Select
              selectedOption={teamFilter}
              onChange={({ detail }) => { setTeamFilter(detail.selectedOption); setCurrentPage(1); }}
              options={teamFilterOptions}
              data-testid="users-team-filter"
            />
            <Select
              selectedOption={roleFilter}
              onChange={({ detail }) => { setRoleFilter(detail.selectedOption); setCurrentPage(1); }}
              options={roleFilterOptions}
              data-testid="users-role-filter"
            />
          </SpaceBetween>
        }
        pagination={
          <Pagination
            currentPageIndex={currentPage}
            pagesCount={totalPages || 1}
            onChange={({ detail }) => setCurrentPage(detail.currentPageIndex)}
          />
        }
        empty={
          <Box textAlign="center" color="inherit" padding="l">
            <SpaceBetween direction="vertical" size="m">
              <b>No users</b>
              <Box variant="p" color="inherit">
                No users found.
              </Box>
              <Button onClick={() => setShowCreateModal(true)}>Create User</Button>
            </SpaceBetween>
          </Box>
        }
      />

      {error && (
        <Alert type="error">{error}</Alert>
      )}

      <CreateUserModal
        visible={showCreateModal}
        onDismiss={() => setShowCreateModal(false)}
        onSubmit={handleCreateUser}
        availableTeams={teams}
      />

      <EditUserModal
        visible={showEditModal}
        onDismiss={() => { setShowEditModal(false); setEditingUser(null); }}
        onSubmit={async (userId, updates) => {
          await updateUser(userId, updates);
          setSuccessMessage(`User updated successfully`);
          setTimeout(() => setSuccessMessage(null), 5000);
        }}
        user={editingUser}
        availableTeams={teams}
      />
    </SpaceBetween>
  );
};

export default UsersListPage;
