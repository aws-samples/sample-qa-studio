import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Table from '@cloudscape-design/components/table';
import Header from '@cloudscape-design/components/header';
import Box from '@cloudscape-design/components/box';
import Link from '@cloudscape-design/components/link';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import { api } from '../../utils/api';

interface TeamUsecase {
  id: string;
  name: string;
  description?: string;
  last_execution_status?: string;
  last_execution_time?: string;
  active?: boolean;
  owner_team_id?: string;
}

interface TeamUsecasesTabProps {
  teamId: string;
}

const TeamUsecasesTab: React.FC<TeamUsecasesTabProps> = ({ teamId }) => {
  const navigate = useNavigate();
  const [usecases, setUsecases] = useState<TeamUsecase[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const data = await api.get('usecases');
        const allUsecases: TeamUsecase[] = data.usecases || [];
        const teamUsecases = allUsecases.filter(uc => uc.owner_team_id === teamId);
        setUsecases(teamUsecases);
      } catch {
        setUsecases([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [teamId]);

  return (
    <Table
      header={
        <Header variant="h2" counter={`(${usecases.length})`}>
          Use Cases
        </Header>
      }
      columnDefinitions={[
        {
          id: 'name',
          header: 'Name',
          cell: (uc: TeamUsecase) => (
            <Link onFollow={(e) => { e.preventDefault(); navigate(`/usecase/${uc.id}`); }}>
              {uc.name}
            </Link>
          ),
        },
        {
          id: 'status',
          header: 'Last Status',
          cell: (uc: TeamUsecase) => {
            if (!uc.last_execution_status) return '-';
            const type = uc.last_execution_status === 'success' ? 'success' : uc.last_execution_status === 'failed' ? 'error' : 'info';
            return <StatusIndicator type={type}>{uc.last_execution_status}</StatusIndicator>;
          },
        },
        {
          id: 'active',
          header: 'Active',
          cell: (uc: TeamUsecase) => uc.active ? 'Yes' : 'No',
        },
      ]}
      items={usecases}
      loading={loading}
      loadingText="Loading use cases..."
      empty={
        <Box textAlign="center" color="inherit">
          <b>No use cases</b>
          <Box variant="p" color="inherit">
            This team has no use cases yet. Create use cases from within an application.
          </Box>
        </Box>
      }
    />
  );
};

export default TeamUsecasesTab;
