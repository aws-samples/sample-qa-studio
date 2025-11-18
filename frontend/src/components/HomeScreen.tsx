import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Link from "@cloudscape-design/components/link";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import ButtonDropdown from "@cloudscape-design/components/button-dropdown";
import Table from "@cloudscape-design/components/table";
import { api } from '../utils/api';
import Badge from "@cloudscape-design/components/badge";
import StatusIndicator from "@cloudscape-design/components/status-indicator";
import ImportUsecaseModal from './ImportUsecaseModal';
import Flashbar from "@cloudscape-design/components/flashbar";
// import { usePreloadOnHover } from './common/ComponentPreloader';

interface BatchExecutionResult {
  usecaseId: string;
  usecaseName: string;
  success: boolean;
  error?: string;
}

interface Usecase {
  id: string;
  name: string;
  description: string;
  active: boolean;
  tags?: string[];
  last_execution_id?: string;
  last_execution_status?: string;
  last_execution_time?: string;
}

// Helper function to format time ago
function formatTimeAgo(timestamp: string): string {
  const now = new Date();
  const past = new Date(timestamp);
  const diffMs = now.getTime() - past.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return past.toLocaleDateString();
}

// Helper function to get status type for StatusIndicator (same as ExecutionHistory)
function getStatusType(status: string) {
  switch (status) {
    case 'success': return 'success';
    case 'error': 
    case 'failed': return 'error';
    case 'executing': return 'in-progress';
    case 'pending': return 'pending';
    default: return 'pending';
  }
}

export default function HomeScreen() {
  const navigate = useNavigate();
  const [usecases, setUsecases] = useState<Usecase[]>([]);
  const [loading, setLoading] = useState(true);
  const [showImportModal, setShowImportModal] = useState(false);
  const [selectedItems, setSelectedItems] = useState<any[]>([]);
  const [batchExecuting, setBatchExecuting] = useState(false);
  const [flashbarItems, setFlashbarItems] = useState<any[]>([]);

  // Preload UsecaseDetail when hovering over usecase links
  // const usecaseDetailPreload = usePreloadOnHover(
  //   'UsecaseDetail',
  //   () => import('./UsecaseDetailRefactored')
  // );

  useEffect(() => {
    const fetchUsecases = async () => {
      try {
        const data = await api.get('usecases');
        setUsecases(data.usecases || []);
      } catch (error) {
        console.error('Failed to fetch usecases:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchUsecases();
  }, []);

  const handleImportSuccess = () => {
    setShowImportModal(false);
    // Refresh the usecases list
    const fetchUsecases = async () => {
      try {
        const data = await api.get('usecases');
        setUsecases(data.usecases || []);
      } catch (error) {
        console.error('Failed to fetch usecases:', error);
      }
    };
    fetchUsecases();
  };

  const handleBatchExecute = async () => {
    if (selectedItems.length === 0) {
      setFlashbarItems([{
        type: 'warning',
        content: 'Please select at least one use case to execute',
        dismissible: true,
        onDismiss: () => setFlashbarItems([])
      }]);
      return;
    }

    setBatchExecuting(true);
    setFlashbarItems([{
      type: 'info',
      content: `Starting batch execution for ${selectedItems.length} use case(s)...`,
      loading: true
    }]);

    // Execute all selected use cases in parallel
    const executionPromises = selectedItems.map(async (usecase) => {
      try {
        await api.post(`usecase/${usecase.id}/execute?trigger-type=OnDemandHeadless`, {});
        return {
          usecaseId: usecase.id,
          usecaseName: usecase.name,
          success: true
        } as BatchExecutionResult;
      } catch (error) {
        return {
          usecaseId: usecase.id,
          usecaseName: usecase.name,
          success: false,
          error: (error as Error).message
        } as BatchExecutionResult;
      }
    });

    const results = await Promise.all(executionPromises);
    
    const successCount = results.filter(r => r.success).length;
    const failureCount = results.filter(r => !r.success).length;

    // Show results
    const resultItems = [];
    
    if (successCount > 0) {
      resultItems.push({
        type: 'success' as const,
        content: `Successfully started execution for ${successCount} use case(s)`,
        dismissible: true,
        onDismiss: () => setFlashbarItems([])
      });
    }

    if (failureCount > 0) {
      const failedUsecases = results
        .filter(r => !r.success)
        .map(r => r.usecaseName)
        .join(', ');
      
      resultItems.push({
        type: 'error' as const,
        content: `Failed to start execution for ${failureCount} use case(s): ${failedUsecases}`,
        dismissible: true,
        onDismiss: () => setFlashbarItems([])
      });
    }

    setFlashbarItems(resultItems);
    setBatchExecuting(false);
    setSelectedItems([]);
  };

  const handleRefresh = async () => {
    setLoading(true);
    try {
      const data = await api.get('usecases');
      setUsecases(data.usecases || []);
    } catch (error) {
      console.error('Failed to fetch usecases:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <SpaceBetween direction="vertical" size="l">
      <Flashbar items={flashbarItems} />
      
      <Header 
        variant="h1"
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            <Button
              iconName="refresh"
              variant="normal"
              onClick={handleRefresh}
              disabled={loading}
              ariaLabel="Refresh use cases"
            />
            <ButtonDropdown
              variant="primary"
              loading={batchExecuting}
              disabled={batchExecuting}
              onItemClick={({ detail }) => {
                if (detail.id === 'import') {
                  setShowImportModal(true);
                } else if (detail.id === 'execute-selected') {
                  handleBatchExecute();
                }
              }}
              items={[
                {
                  id: 'execute-selected',
                  text: `Execute Selected (${selectedItems.length})`,
                  disabled: selectedItems.length === 0
                },
                {
                  id: 'import',
                  text: 'Import Use Case'
                }
              ]}
              mainAction={{
                text: 'Create Use Case',
                onClick: () => navigate('/create-usecase')
              }}
            />
          </SpaceBetween>
        }
      >
        Use Cases
      </Header>
      <Table
        columnDefinitions={[
          { 
            id: 'name', 
            header: 'Name',
            maxWidth: 300,
            cell: item => (
              <div>
                <Link href={`/usecase/${item.id}`}>
                  {item.name}
                </Link>
                {item.description && (
                  <div style={{ fontSize: '0.85em', color: '#5f6b7a', marginTop: '4px' }}>
                    {item.description}
                  </div>
                )}
              </div>
            )
          },
          { 
            id: 'last_execution_status', 
            header: 'Last Status', 
            cell: item => {
              if (!item.last_execution_status) {
                return <StatusIndicator type="stopped">Never run</StatusIndicator>;
              }
              
              return (
                <StatusIndicator type={getStatusType(item.last_execution_status)}>
                  {item.last_execution_status}
                </StatusIndicator>
              );
            }
          },
          { 
            id: 'last_execution_time', 
            header: 'Last Execution', 
            cell: item => {
              if (!item.last_execution_time) {
                return '-';
              }
              
              const timeAgo = formatTimeAgo(item.last_execution_time);
              const fullDate = new Date(item.last_execution_time).toLocaleString();
              
              return (
                <span title={fullDate} style={{ fontSize: '0.9em' }}>
                  {timeAgo}
                </span>
              );
            }
          },
          { 
            id: 'active', 
            header: 'Active', 
            cell: item => item.active ? (
              <Badge color="green">Active</Badge>
            ) : (
              <Badge color="red">Inactive</Badge>
            )
          },
          { 
            id: 'tags', 
            header: 'Tags', 
            cell: item => item.tags ? (
              <SpaceBetween direction="horizontal" size="xs">
                {item.tags.map((tag: string) => (<Badge key={tag}>{tag}</Badge>))}
              </SpaceBetween>
            ) : ''
          }
        ]}
        items={usecases}
        loading={loading}
        loadingText="Loading use cases..."
        empty="No use cases found"
        selectionType="multi"
        selectedItems={selectedItems}
        onSelectionChange={({ detail }) => setSelectedItems(detail.selectedItems)}
        resizableColumns
      />
      
      <ImportUsecaseModal
        visible={showImportModal}
        onDismiss={() => setShowImportModal(false)}
        onImportSuccess={handleImportSuccess}
      />
    </SpaceBetween>
  );
}