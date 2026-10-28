import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Table from '@cloudscape-design/components/table';
import Header from '@cloudscape-design/components/header';
import Box from '@cloudscape-design/components/box';
import Link from '@cloudscape-design/components/link';
import Badge from '@cloudscape-design/components/badge';
import { api } from '../../utils/api';

interface TeamApp {
  id: string;
  name: string;
  usecase_count: number;
  last_execution_at?: string;
  shared_from?: string;
}

interface ApplicationsTabProps {
  teamId: string;
}

const ApplicationsTab: React.FC<ApplicationsTabProps> = ({ teamId }) => {
  const navigate = useNavigate();
  const [apps, setApps] = useState<TeamApp[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const data = await api.get(`teams/${encodeURIComponent(teamId)}/applications`);
        setApps(Array.isArray(data) ? data : []);
      } catch {
        setApps([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [teamId]);

  return (
    <Table
      header={
        <Header variant="h2" counter={`(${apps.length})`}>
          Applications
        </Header>
      }
      columnDefinitions={[
        {
          id: 'name',
          header: 'Application',
          cell: (app: TeamApp) => (
            <Link
              onFollow={(e) => {
                e.preventDefault();
                navigate(`/applications/${app.id}`);
              }}
            >
              {app.name}
            </Link>
          ),
        },
        {
          id: 'usecases',
          header: 'Test Cases',
          cell: (app: TeamApp) => app.usecase_count || 0,
        },
        {
          id: 'lastRun',
          header: 'Last Run',
          cell: (app: TeamApp) =>
            app.last_execution_at
              ? new Date(app.last_execution_at).toLocaleString()
              : '-',
        },
        {
          id: 'shared',
          header: '',
          cell: (app: TeamApp) =>
            app.shared_from ? (
              <Badge color="blue">Shared from {app.shared_from}</Badge>
            ) : null,
        },
      ]}
      items={apps}
      loading={loading}
      loadingText="Loading applications..."
      empty={
        <Box textAlign="center" color="inherit">
          <b>No applications</b>
          <Box variant="p" color="inherit">
            This team has no applications assigned yet.
          </Box>
        </Box>
      }
    />
  );
};

export default ApplicationsTab;
