import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';
import BreadcrumbGroup from '@cloudscape-design/components/breadcrumb-group';
import Tabs from '@cloudscape-design/components/tabs';
import Spinner from '@cloudscape-design/components/spinner';
import Box from '@cloudscape-design/components/box';
import Alert from '@cloudscape-design/components/alert';
import { api } from '../../utils/api';
import { usePermissions } from '../../auth';
import { Team } from '../../types/permissions';
import MembersTab from './MembersTab';
import ApplicationsTab from './ApplicationsTab';
import SharedAccessTab from './SharedAccessTab';
import DeleteConfirmationModal from './DeleteConfirmationModal';

const TeamDetailPage: React.FC = () => {
  const { id: teamId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { isAdmin } = usePermissions();

  const [team, setTeam] = useState<Team | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  useEffect(() => {
    async function load() {
      if (!teamId) return;
      try {
        setLoading(true);
        const data = await api.get(`teams/${encodeURIComponent(teamId)}`);
        setTeam(data);
      } catch (err: any) {
        setError(err.message || 'Failed to load team');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [teamId]);

  const handleDelete = async () => {
    if (!teamId) return;
    await api.delete(`teams/${encodeURIComponent(teamId)}`);
    navigate('/admin/teams');
  };

  if (loading) {
    return (
      <Box textAlign="center" padding="xxl">
        <Spinner size="large" />
      </Box>
    );
  }

  if (error || !team) {
    return (
      <Alert type="error">{error || 'Team not found'}</Alert>
    );
  }

  return (
    <SpaceBetween direction="vertical" size="l">
      <BreadcrumbGroup
        items={[
          { text: 'Teams', href: '/admin/teams' },
          { text: team.name, href: '#' },
        ]}
        onFollow={(e) => {
          e.preventDefault();
          if (e.detail.href !== '#') {
            navigate(e.detail.href);
          }
        }}
      />

      <Header
        variant="h1"
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            {isAdmin && (
              <Button
                onClick={() => setShowDeleteModal(true)}
                data-testid="delete-team-button"
              >
                Delete
              </Button>
            )}
          </SpaceBetween>
        }
        description={`${team.memberCount} members, ${team.applicationCount} applications`}
      >
        {team.name}
      </Header>

      <Tabs
        tabs={[
          {
            id: 'members',
            label: 'Members',
            content: <MembersTab teamId={teamId!} />,
          },
          {
            id: 'applications',
            label: 'Applications',
            content: <ApplicationsTab teamId={teamId!} />,
          },
          {
            id: 'shared-access',
            label: 'Shared Access',
            content: <SharedAccessTab teamId={teamId!} />,
          },
        ]}
      />

      <DeleteConfirmationModal
        visible={showDeleteModal}
        onDismiss={() => setShowDeleteModal(false)}
        onConfirm={handleDelete}
        entityType="Team"
        entityName={team.name}
        memberCount={team.memberCount}
      />
    </SpaceBetween>
  );
};

export default TeamDetailPage;
