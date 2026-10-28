import React, { useState, useEffect } from 'react';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
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
import TeamUsecasesTab from './TeamUsecasesTab';

const MyTeamPage: React.FC = () => {
  const { teams: userTeams } = usePermissions();

  const [team, setTeam] = useState<Team | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Use the first team from user's memberships
  const myTeamId = userTeams.length > 0 ? userTeams[0].team_id : null;

  useEffect(() => {
    async function load() {
      if (!myTeamId) {
        setLoading(false);
        return;
      }
      try {
        setLoading(true);
        const data = await api.get(`teams/${encodeURIComponent(myTeamId)}`);
        setTeam(data);
      } catch (err: any) {
        setError(err.message || 'Failed to load team');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [myTeamId]);

  if (loading) {
    return (
      <Box textAlign="center" padding="xxl">
        <Spinner size="large" />
      </Box>
    );
  }

  if (!myTeamId) {
    return (
      <Alert type="info">
        You are not assigned to any team. Contact your administrator to be added to a team.
      </Alert>
    );
  }

  if (error || !team) {
    return (
      <Alert type="error">{error || 'Team not found'}</Alert>
    );
  }

  return (
    <SpaceBetween direction="vertical" size="l">
      <Header
        variant="h1"
        description={`${team.memberCount} members, ${team.applicationCount} applications`}
      >
        My Team: {team.name}
      </Header>

      <Tabs
        tabs={[
          {
            id: 'members',
            label: 'Members',
            content: <MembersTab teamId={myTeamId} />,
          },
          {
            id: 'applications',
            label: 'Applications',
            content: <ApplicationsTab teamId={myTeamId} />,
          },
          {
            id: 'usecases',
            label: 'Use Cases',
            content: <TeamUsecasesTab teamId={myTeamId} />,
          },
          {
            id: 'shared-access',
            label: 'Shared Access',
            content: <SharedAccessTab teamId={myTeamId} />,
          },
        ]}
      />
    </SpaceBetween>
  );
};

export default MyTeamPage;
