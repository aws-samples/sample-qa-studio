import React, { useState } from 'react';
import Header from "@cloudscape-design/components/header";
import Button from "@cloudscape-design/components/button";
import Table from "@cloudscape-design/components/table";
import StatusIndicator from "@cloudscape-design/components/status-indicator";
import Box from "@cloudscape-design/components/box";
import Flashbar, { FlashbarProps } from "@cloudscape-design/components/flashbar";
import SpaceBetween from "@cloudscape-design/components/space-between";
import { api, ExecutionModel, executionIdOf } from '../../utils/api';
import { formatDateTime } from '../../utils/dateFormat';
import { executionStatusType } from '../../utils/executionStatus';
import { useApiData } from '../common/useAsyncData';
import { ContainerLoading } from '../common/LoadingStates';
import DeleteConfirmModal from '../common/DeleteConfirmModal';

interface ExecutionHistoryProps {
  usecaseId: string;
  /** Bare execution id of the selected row; `null` for no selection. Controlled by the parent. */
  selectedExecutionId: string | null;
  onSelectExecution: (id: string | null) => void;
}

export default function ExecutionHistory({ usecaseId, selectedExecutionId, onSelectExecution }: ExecutionHistoryProps) {
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [flashbarItems, setFlashbarItems] = useState<FlashbarProps.MessageDefinition[]>([]);

  const { data: executionsData, loading, refetch } = useApiData(
    () => api.get(`usecase/${usecaseId}/executions`),
    [usecaseId]
  );

  const executions: ExecutionModel[] = executionsData?.executions || [];
  const selectedExecution = executions.find((item) => executionIdOf(item) === selectedExecutionId) ?? null;
  const selectedItems = selectedExecution ? [selectedExecution] : [];

  const showFlash = (type: 'success' | 'error', content: string) => {
    setFlashbarItems([{ type, content, dismissible: true, onDismiss: () => setFlashbarItems([]) }]);
  };

  const handleDelete = async () => {
    if (!selectedExecution) return;
    const executionId = executionIdOf(selectedExecution);
    setShowDeleteModal(false);
    setDeleting(true);
    try {
      await api.delete(`usecase/${usecaseId}/executions/${executionId}`);
      showFlash('success', `Deleted execution ${executionId}`);
      await refetch();
      onSelectExecution(null);
    } catch (error) {
      console.error('Failed to delete execution:', { usecaseId, executionId, error });
      showFlash('error', `Failed to delete execution ${executionId}: ${(error as Error).message}`);
    } finally {
      setDeleting(false);
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

      <Table
        header={
          <Header
            variant="h2"
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
                  onClick={() => setShowDeleteModal(true)}
                  disabled={!selectedExecution || deleting}
                  loading={deleting}
                >
                  Delete
                </Button>
              </SpaceBetween>
            }
          >
            Execution History
          </Header>
        }
        columnDefinitions={[
          {
            id: 'pk',
            header: 'Execution ID',
            cell: (item: ExecutionModel) => executionIdOf(item),
          },
          {
            id: 'status',
            header: 'Status',
            cell: item => (
              <StatusIndicator type={executionStatusType(item.status)}>
                {item.status}
              </StatusIndicator>
            ),
          },
          {
            id: 'created_at',
            header: 'Created',
            cell: item => formatDateTime(item.created_at),
          },
          {
            id: 'trigger_type',
            header: 'Trigger',
            cell: item => item.trigger_type || 'Manual',
          }
        ]}
        items={executions}
        trackBy="sk"
        selectionType="single"
        selectedItems={selectedItems}
        onSelectionChange={({ detail }) => {
          const [selected] = detail.selectedItems;
          onSelectExecution(selected ? executionIdOf(selected) : null);
        }}
        empty={
          <Box textAlign="center">
            <Box variant="strong">No executions</Box>
            <Box variant="p" color="text-body-secondary">
              No executions have been run for this usecase yet.
            </Box>
          </Box>
        }
      />

      <DeleteConfirmModal
        visible={showDeleteModal}
        count={1}
        noun={{ singular: 'execution', plural: 'executions', title: 'Executions' }}
        consequences="This will remove all associated data including steps, logs, and results."
        onDismiss={() => setShowDeleteModal(false)}
        onConfirm={handleDelete}
        loading={deleting}
      />
    </SpaceBetween>
  );
}
