import React, { useEffect, useState } from 'react';
import Table from '@cloudscape-design/components/table';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';
import Box from '@cloudscape-design/components/box';
import Badge from '@cloudscape-design/components/badge';
import { useSharedAccess } from '../../hooks/useSharedAccess';
import { useTeams } from '../../hooks/useTeams';
import { useApplications } from '../../hooks/useApplications';
import { usePermissions } from '../../auth';
import { SharedAccessGrant } from '../../types/permissions';
import GrantAccessModal from './GrantAccessModal';

interface SharedAccessTabProps {
  teamId: string;
}

const LEVEL_COLORS: Record<string, 'blue' | 'green' | 'red'> = {
  view: 'blue',
  execute: 'green',
  full: 'red',
};

const SharedAccessTab: React.FC<SharedAccessTabProps> = ({ teamId }) => {
  const { grants, loading, fetchGrants, grantAccess, revokeAccess } = useSharedAccess(teamId);
  const { teams } = useTeams();
  const { applications } = useApplications();
  const { isAdmin, isTeamLead } = usePermissions();
  const [showGrantModal, setShowGrantModal] = useState(false);

  useEffect(() => {
    fetchGrants();
  }, [fetchGrants]);

  const canManageSharing = isAdmin || isTeamLead;

  // Exclude current team from grant targets
  const availableTeams = teams.filter((t) => t.id !== teamId);
  const availableApps = applications.map((a) => ({ id: a.id, name: a.name }));

  return (
    <SpaceBetween direction="vertical" size="l">
      <Table
        header={
          <Header
            variant="h2"
            actions={
              canManageSharing && (
                <Button
                  onClick={() => setShowGrantModal(true)}
                  data-testid="grant-access-button"
                >
                  Grant Access
                </Button>
              )
            }
            counter={`(${grants.length})`}
          >
            Shared Access
          </Header>
        }
        columnDefinitions={[
          {
            id: 'targetTeam',
            header: 'Team',
            cell: (g: SharedAccessGrant) => g.targetTeamName || g.targetTeamId,
          },
          {
            id: 'accessLevel',
            header: 'Access Level',
            cell: (g: SharedAccessGrant) => (
              <Badge color={LEVEL_COLORS[g.accessLevel] || 'blue'}>
                {g.accessLevel}
              </Badge>
            ),
          },
          {
            id: 'grantedAt',
            header: 'Granted',
            cell: (g: SharedAccessGrant) =>
              g.grantedAt ? new Date(g.grantedAt).toLocaleDateString() : '-',
          },
          {
            id: 'actions',
            header: 'Actions',
            cell: (g: SharedAccessGrant) =>
              canManageSharing && (
                <Button
                  variant="link"
                  onClick={() => revokeAccess(g.grantId)}
                  data-testid={`revoke-access-${g.grantId}`}
                >
                  Revoke
                </Button>
              ),
          },
        ]}
        items={grants}
        loading={loading}
        loadingText="Loading shared access..."
        empty={
          <Box textAlign="center" color="inherit">
            <b>No shared access grants</b>
            <Box variant="p" color="inherit">
              This team has not shared any applications with other teams.
            </Box>
            {canManageSharing && (
              <Button onClick={() => setShowGrantModal(true)}>Grant Access</Button>
            )}
          </Box>
        }
      />

      <GrantAccessModal
        visible={showGrantModal}
        onDismiss={() => setShowGrantModal(false)}
        onSubmit={grantAccess}
        availableTeams={availableTeams}
        availableApps={availableApps}
      />
    </SpaceBetween>
  );
};

export default SharedAccessTab;
