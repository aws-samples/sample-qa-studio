import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import Button from "@cloudscape-design/components/button";
import Table from "@cloudscape-design/components/table";
import Link from "@cloudscape-design/components/link";
import StatusIndicator from "@cloudscape-design/components/status-indicator";
import Box from "@cloudscape-design/components/box";
import Flashbar from "@cloudscape-design/components/flashbar";
import { api, ExecutionModel } from '../../utils/api';
import { useApiData } from '../common/useAsyncData';
import { ContainerLoading } from '../common/LoadingStates';
import { SpaceBetween } from '@cloudscape-design/components';
import DeleteExecutionsModal from '../DeleteExecutionsModal';

interface ExecutionHistoryProps {
  usecaseId: string;
}

interface BatchDeleteResult {
  executionId: string;
  success: boolean;
  error?: string;
}

export default function ExecutionHistory({ usecaseId }: ExecutionHistoryProps) {
  const navigate = useNavigate();
  const [selectedItems, setSelectedItems] = useState<ExecutionModel[]>([]);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [flashbarItems, setFlashbarItems] = useState<any[]>([]);

  const { data: executionsData, loading, refetch } = useApiData(
    () => api.get(`usecase/${usecaseId}/executions`),
    [usecaseId]
  );

  const executions = executionsData?.executions || [];

  const handleDeleteClick = () => {
    if (selectedItems.length === 0) {
      setFlashbarItems([{
        type: 'warning',
        content: 'Please select at least one execution to delete',
        dismissible: true,
        onDismiss: () => setFlashbarItems([])
      }]);
      return;
    }
    setShowDeleteModal(true);
  };

  const handleBatchDelete = async () => {
    setShowDeleteModal(false);
    setDeleting(true);
    setFlashbarItems([{
      type: 'info',
      content: `Deleting ${selectedItems.length} execution(s)...`,
      loading: true
    }]);

    const deletePromises = selectedItems.map(async (execution) => {
      try {
        const cleanExecutionId = execution.sk.replace('EXECUTION#', '');
        await api.delete(`usecase/${usecaseId}/executions/${cleanExecutionId}`);
        return {
          executionId: cleanExecutionId,
          success: true
        } as BatchDeleteResult;
      } catch (error) {
        return {
          executionId: execution.sk.replace('EXECUTION#', ''),
          success: false,
          error: (error as Error).message
        } as BatchDeleteResult;
      }
    });

    const results = await Promise.all(deletePromises);
    
    const successCount = results.filter(r => r.success).length;
    const failureCount = results.filter(r => !r.success).length;

    const resultItems = [];
    
    if (successCount > 0) {
      resultItems.push({
        type: 'success' as const,
        content: `Successfully deleted ${successCount} execution(s)`,
        dismissible: true,
        onDismiss: () => setFlashbarItems([])
      });
    }

    if (failureCount > 0) {
      const failedExecutions = results
        .filter(r => !r.success)
        .map(r => r.executionId)
        .join(', ');
      
      resultItems.push({
        type: 'error' as const,
        content: `Failed to delete ${failureCount} execution(s): ${failedExecutions}`,
        dismissible: true,
        onDismiss: () => setFlashbarItems([])
      });
    }

    setFlashbarItems(resultItems);
    setSelectedItems([]);
    setDeleting(false);
    await refetch();
  };

  const getStatusType = (status: string) => {
    switch (status) {
      case 'success': return 'success';
      case 'error':
      case 'failed': return 'error';
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
      <Flashbar items={flashbarItems} />
      
      <Header
        variant="h1"
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            <Button
              iconName="refresh"
              onClick={refetch}
              disabled={loading || deleting}
              ariaLabel="Refresh execution history"
            >
              Refresh
            </Button>
            <Button
              iconName="remove"
              onClick={handleDeleteClick}
              disabled={selectedItems.length === 0 || deleting}
              loading={deleting}
            >
              Delete Selected ({selectedItems.length})
            </Button>
          </SpaceBetween>
        }
      />
      <Table
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
            id: 'created_at', 
            header: 'Created', 
            cell: item => new Date(item.created_at).toLocaleString(),
          },
          { 
            id: 'trigger_type', 
            header: 'Trigger', 
            cell: item => item.trigger_type || 'Manual',
          }
        ]}
        items={executions}
        selectionType="multi"
        selectedItems={selectedItems}
        onSelectionChange={({ detail }) => setSelectedItems(detail.selectedItems)}
        empty={
          <Box textAlign="center">
            <Box variant="strong">No executions</Box>
            <Box variant="p" color="text-body-secondary">
              No executions have been run for this usecase yet.
            </Box>
          </Box>
        }
      />

      <DeleteExecutionsModal
        visible={showDeleteModal}
        executionCount={selectedItems.length}
        onDismiss={() => setShowDeleteModal(false)}
        onConfirm={handleBatchDelete}
        deleting={deleting}
      />
    </SpaceBetween>
  );
}