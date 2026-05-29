import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Box from '@cloudscape-design/components/box';
import Button from '@cloudscape-design/components/button';
import Header from '@cloudscape-design/components/header';
import Link from '@cloudscape-design/components/link';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Table from '@cloudscape-design/components/table';
import Spinner from '@cloudscape-design/components/spinner';
import Alert from '@cloudscape-design/components/alert';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import { CreateApplicationModal } from './dashboard/CreateApplicationModal';
import { Application } from '../types/application';
import { api } from '../utils/api';

export default function ApplicationSettings() {
  const navigate = useNavigate();
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [createModalVisible, setCreateModalVisible] = useState(false);

  useEffect(() => {
    loadApplications();
  }, []);

  async function loadApplications() {
    setLoading(true);
    setError('');
    try {
      const data = await api.get('applications');
      setApplications(data);
    } catch (e: any) {
      setError(e.message || 'Failed to load applications');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return <Box textAlign="center" padding="xxl"><Spinner size="large" /></Box>;
  }

  return (
    <SpaceBetween size="l">
      {error && <Alert type="error" dismissible onDismiss={() => setError('')}>{error}</Alert>}

      <Table
        header={
          <Header
            variant="h1"
            actions={
              <Button variant="primary" onClick={() => setCreateModalVisible(true)}>
                Create application
              </Button>
            }
          >
            Applications
          </Header>
        }
        items={applications}
        trackBy="id"
        columnDefinitions={[
          { id: 'name', header: 'Name', cell: (item) => (
            <Link onFollow={() => navigate(`/applications/${item.id}`)}>{item.name}</Link>
          ), sortingField: 'name' },
          { id: 'base_url', header: 'Base URL', cell: (item) => item.base_url },
          { id: 'team', header: 'Team', cell: (item) => item.team || '-' },
          { id: 'usecase_count', header: 'Usecases', cell: (item) => item.usecase_count },
          {
            id: 'last_execution',
            header: 'Last Execution',
            cell: (item) => item.last_execution_status ? (
              <StatusIndicator type={item.last_execution_status === 'success' ? 'success' : 'error'}>
                {item.last_execution_status}
              </StatusIndicator>
            ) : '-',
          },
        ]}
        empty={
          <Box textAlign="center" padding="l">
            <SpaceBetween size="m">
              <Box variant="p">No applications yet</Box>
              <Button onClick={() => setCreateModalVisible(true)}>Create your first application</Button>
            </SpaceBetween>
          </Box>
        }
      />

      <CreateApplicationModal
        visible={createModalVisible}
        onDismiss={() => setCreateModalVisible(false)}
        onSuccess={loadApplications}
      />
    </SpaceBetween>
  );
}
