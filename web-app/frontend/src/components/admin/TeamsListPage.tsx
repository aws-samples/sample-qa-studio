import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Table from '@cloudscape-design/components/table';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';
import Box from '@cloudscape-design/components/box';
import TextFilter from '@cloudscape-design/components/text-filter';
import Pagination from '@cloudscape-design/components/pagination';
import Link from '@cloudscape-design/components/link';
import Alert from '@cloudscape-design/components/alert';
import { useTeams } from '../../hooks/useTeams';
import { usePermissions } from '../../auth';
import { Team } from '../../types/permissions';
import CreateTeamModal from './CreateTeamModal';
import DeleteConfirmationModal from './DeleteConfirmationModal';

const PAGE_SIZE = 10;

const TeamsListPage: React.FC = () => {
  const navigate = useNavigate();
  const { teams, loading, error, createTeam, deleteTeam } = useTeams();
  const { isAdmin } = usePermissions();

  const [filterText, setFilterText] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [teamToDelete, setTeamToDelete] = useState<Team | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Filter teams by search text
  const filteredTeams = teams.filter((t) =>
    t.name.toLowerCase().includes(filterText.toLowerCase())
  );

  // Paginate
  const totalPages = Math.ceil(filteredTeams.length / PAGE_SIZE);
  const paginatedTeams = filteredTeams.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE
  );

  const handleCreateTeam = async (name: string) => {
    await createTeam(name);
    setSuccessMessage(`Team "${name}" created successfully`);
    setTimeout(() => setSuccessMessage(null), 5000);
  };

  const handleDeleteTeam = async () => {
    if (!teamToDelete) return;
    try {
      await deleteTeam(teamToDelete.id);
      setSuccessMessage(`Team "${teamToDelete.name}" deleted`);
      setTeamToDelete(null);
      setTimeout(() => setSuccessMessage(null), 5000);
    } catch (err: any) {
      setActionError(err.message || 'Failed to delete team');
    }
  };

  return (
    <SpaceBetween direction="vertical" size="l">
      {actionError && (
        <Alert type="error" dismissible onDismiss={() => setActionError(null)}>
          {actionError}
        </Alert>
      )}
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
              <SpaceBetween direction="horizontal" size="xs">
                {isAdmin && (
                  <Button
                    variant="primary"
                    onClick={() => setShowCreateModal(true)}
                    data-testid="create-team-button"
                  >
                    Create Team
                  </Button>
                )}
              </SpaceBetween>
            }
            counter={`(${filteredTeams.length})`}
          >
            Teams
          </Header>
        }
        columnDefinitions={[
          {
            id: 'name',
            header: 'Team Name',
            cell: (team: Team) => (
              <Link
                onFollow={(e) => {
                  e.preventDefault();
                  navigate(`/admin/teams/${team.id}`);
                }}
                data-testid={`team-link-${team.id}`}
              >
                {team.name}
              </Link>
            ),
            sortingField: 'name',
          },
          {
            id: 'memberCount',
            header: 'Members',
            cell: (team: Team) => team.memberCount,
            sortingField: 'memberCount',
          },
          {
            id: 'applicationCount',
            header: 'Applications',
            cell: (team: Team) => team.applicationCount,
            sortingField: 'applicationCount',
          },
          {
            id: 'actions',
            header: 'Actions',
            cell: (team: Team) => (
              <SpaceBetween direction="horizontal" size="xs">
                <Button
                  variant="link"
                  onClick={() => navigate(`/admin/teams/${team.id}`)}
                  data-testid={`team-edit-${team.id}`}
                >
                  Edit
                </Button>
                {isAdmin && (
                  <Button
                    variant="link"
                    onClick={() => setTeamToDelete(team)}
                    data-testid={`team-delete-${team.id}`}
                  >
                    Delete
                  </Button>
                )}
              </SpaceBetween>
            ),
          },
        ]}
        items={paginatedTeams}
        loading={loading}
        loadingText="Loading teams..."
        filter={
          <TextFilter
            filteringText={filterText}
            onChange={({ detail }) => {
              setFilterText(detail.filteringText);
              setCurrentPage(1);
            }}
            filteringPlaceholder="Find teams"
            data-testid="teams-filter"
          />
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
              <b>No teams</b>
              <Box variant="p" color="inherit">
                No teams have been created yet.
              </Box>
              {isAdmin && (
                <Button onClick={() => setShowCreateModal(true)} data-testid="empty-create-team">
                  Create Team
                </Button>
              )}
            </SpaceBetween>
          </Box>
        }
      />

      {error && (
        <Alert type="error">{error}</Alert>
      )}

      <CreateTeamModal
        visible={showCreateModal}
        onDismiss={() => setShowCreateModal(false)}
        onSubmit={handleCreateTeam}
      />

      <DeleteConfirmationModal
        visible={teamToDelete !== null}
        onDismiss={() => setTeamToDelete(null)}
        onConfirm={handleDeleteTeam}
        entityType="Team"
        entityName={teamToDelete?.name || ''}
        memberCount={teamToDelete?.memberCount || 0}
      />
    </SpaceBetween>
  );
};

export default TeamsListPage;
