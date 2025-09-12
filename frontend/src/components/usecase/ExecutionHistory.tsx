import React from 'react';
import { useNavigate } from 'react-router-dom';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import Button from "@cloudscape-design/components/button";
import Table from "@cloudscape-design/components/table";
import Link from "@cloudscape-design/components/link";
import StatusIndicator from "@cloudscape-design/components/status-indicator";
import Box from "@cloudscape-design/components/box";
import { api, ExecutionModel } from '../../utils/api';
import { useApiData } from '../common/useAsyncData';
import { ContainerLoading } from '../common/LoadingStates';
import { SpaceBetween } from '@cloudscape-design/components';

interface ExecutionHistoryProps {
  usecaseId: string;
}

export default function ExecutionHistory({ usecaseId }: ExecutionHistoryProps) {
  const navigate = useNavigate();

  const { data: executionsData, loading, refetch } = useApiData(
    () => api.get(`usecase/${usecaseId}/executions`),
    [usecaseId]
  );

  const executions = executionsData?.executions || [];

  const handleDeleteExecution = async (executionId: string) => {
    try {
      const cleanExecutionId = executionId.replace('EXECUTION#', '');
      await api.delete(`usecase/${usecaseId}/executions/${cleanExecutionId}`);
      await refetch();
    } catch (error) {
      console.error('Failed to delete execution:', error);
    }
  };

  const getStatusType = (status: string) => {
    switch (status) {
      case 'success': return 'success';
      case 'error': return 'error';
      case 'executing': return 'in-progress';
      default: return 'pending';
    }
  };

  if (loading) {
    return (
      <ContainerLoading 
        title="Execution History"
        text="Loading execution history..."
      />
    );
  }

  return (
    <SpaceBetween direction='vertical' size="m">
      <Header
        variant="h1"
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            <Button
              iconName="refresh"
              onClick={refetch}
              disabled={loading}
              ariaLabel="Refresh execution history"
            >
              Refresh
            </Button>
          </SpaceBetween>
        }
      />
      <Table
        // variant="embedded"
        columnDefinitions={[
          { 
            id: 'pk', 
            header: 'Execution ID', 
            cell: (item: ExecutionModel) => (
              <Link onClick={() => navigate(`/usecase/${usecaseId}/execution/${item.sk.replace('EXECUTION#', '')}`)}>  
                {item.sk.replace('EXECUTION#', '')}
              </Link>
            ),
          },
          { 
            id: 'status', 
            header: 'Status', 
            cell: item => (
              <StatusIndicator type={getStatusType(item.status)}>
                {item.status}
              </StatusIndicator>
            ),
          },
          { 
            id: 'createdAt', 
            header: 'Created', 
            cell: item => new Date(item.createdAt).toLocaleString(),
          },
          { 
            id: 'triggerType', 
            header: 'Trigger', 
            cell: item => item.triggerType || 'Manual',
          },
          { 
            id: 'actions', 
            header: 'Actions', 
            cell: item => (
              <Link onClick={() => handleDeleteExecution(item.sk)}>Delete</Link>
            ),
          }
        ]}
        items={executions}
        empty={
          <Box textAlign="center">
            <Box variant="strong">No executions</Box>
            <Box variant="p" color="text-body-secondary">
              No executions have been run for this usecase yet.
            </Box>
          </Box>
        }
      />
    </SpaceBetween>
  );
}