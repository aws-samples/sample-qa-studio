import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import Link from "@cloudscape-design/components/link";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import ButtonDropdown from "@cloudscape-design/components/button-dropdown";
import Table from "@cloudscape-design/components/table";
import TextFilter from "@cloudscape-design/components/text-filter";
import { api } from '../utils/api';
import { batchedPromiseAll } from '../utils/batchedPromiseAll';
import Badge from "@cloudscape-design/components/badge";
import StatusIndicator from "@cloudscape-design/components/status-indicator";
import DeleteUsecaseModal from './DeleteUsecaseModal';
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
  test_platform?: string;
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
    case 'running':
    case 'executing': return 'in-progress';
    case 'pending': return 'pending';
    case 'stopped': return 'stopped';
    default: return 'pending';
  }
}

export default function HomeScreen() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [usecases, setUsecases] = useState<Usecase[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [selectedItems, setSelectedItems] = useState<any[]>([]);
  const [batchExecuting, setBatchExecuting] = useState(false);
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [flashbarItems, setFlashbarItems] = useState<any[]>([]);
  const [sortingColumn, setSortingColumn] = useState<any>({ sortingField: 'name' });
  const [sortingDescending, setSortingDescending] = useState(false);

  // Get filter text from URL parameter
  const filteringText = searchParams.get('search') || '';

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

  const handleDeleteClick = () => {
    if (selectedItems.length === 0) {
      setFlashbarItems([{
        type: 'warning',
        content: 'Please select at least one use case to delete',
        dismissible: true,
        onDismiss: () => setFlashbarItems([])
      }]);
      return;
    }
    setShowDeleteModal(true);
  };

  const handleBatchDelete = async () => {
    setShowDeleteModal(false);
    setBatchDeleting(true);
    setFlashbarItems([{
      type: 'info',
      content: `Deleting ${selectedItems.length} use case(s)...`,
      loading: true
    }]);

    // Delete selected use cases in batches matching Lambda concurrency limit
    const results = await batchedPromiseAll(selectedItems, async (usecase) => {
      try {
        await api.delete(`usecase/${usecase.id}`);
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

    const successCount = results.filter(r => r.success).length;
    const failureCount = results.filter(r => !r.success).length;

    // Show results
    const resultItems = [];

    if (successCount > 0) {
      resultItems.push({
        type: 'success' as const,
        content: `Successfully deleted ${successCount} use case(s)`,
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
        content: `Failed to delete ${failureCount} use case(s): ${failedUsecases}`,
        dismissible: true,
        onDismiss: () => setFlashbarItems([])
      });
    }

    setFlashbarItems(resultItems);
    setSelectedItems([]);
    setBatchDeleting(false);

    // Refresh the list
    try {
      const data = await api.get('usecases');
      setUsecases(data.usecases || []);
    } catch (error) {
      console.error('Failed to fetch usecases:', error);
    }
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

  // Filter usecases based on search text
  const filteredUsecases = usecases.filter(usecase => {
    if (!filteringText) return true;

    const searchText = filteringText.toLowerCase();
    const nameMatch = usecase.name?.toLowerCase().includes(searchText) || false;
    const descriptionMatch = usecase.description?.toLowerCase().includes(searchText) || false;
    const tagsMatch = usecase.tags?.some(tag => tag?.toLowerCase().includes(searchText)) || false;
    const statusMatch = usecase.last_execution_status?.toLowerCase().includes(searchText) || false;

    return nameMatch || descriptionMatch || tagsMatch || statusMatch;
  });

  // Sort filtered usecases
  const sortedUsecases = [...filteredUsecases].sort((a, b) => {
    const field = sortingColumn?.sortingField;
    if (!field) return 0;

    let cmp = 0;
    switch (field) {
      case 'name':
        cmp = (a.name || '').localeCompare(b.name || '');
        break;
      case 'last_execution_status':
        cmp = (a.last_execution_status || '').localeCompare(b.last_execution_status || '');
        break;
      case 'last_execution_time':
        cmp = (a.last_execution_time || '').localeCompare(b.last_execution_time || '');
        break;
      case 'active':
        cmp = (a.active === b.active) ? 0 : a.active ? -1 : 1;
        break;
      default:
        cmp = 0;
    }
    return sortingDescending ? -cmp : cmp;
  });

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
              loading={batchExecuting || batchDeleting}
              disabled={batchExecuting || batchDeleting || loading}
              onItemClick={({ detail }) => {
                if (detail.id === 'execute-selected') {
                  handleBatchExecute();
                } else if (detail.id === 'delete-selected') {
                  handleDeleteClick();
                }
              }}
              items={[
                {
                  id: 'execute-selected',
                  text: `Execute Selected (${selectedItems.length})`,
                  disabled: selectedItems.length === 0
                },
                {
                  id: 'delete-selected',
                  text: `Delete Selected (${selectedItems.length})`,
                  disabled: selectedItems.length === 0
                }
              ]}
              mainAction={{
                text: 'Create Use Case',
                onClick: () => navigate('/create')
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
            sortingField: 'name',
            minWidth: 450,
            cell: item => (
              <div>
                <Link href={`/usecase/${item.id}`}>
                  {item.name}
                </Link>
                {item.description && (
                  <div style={{ fontSize: '0.85em', color: '#5f6b7a', marginTop: '4px', whiteSpace: 'pre-line' }}>
                    {item.description}
                  </div>
                )}
              </div>
            )
          },
          {
            id: 'test_platform',
            header: 'Platform',
            width: 100,
            cell: item => {
              const platform = item.test_platform || 'web';
              return platform === 'mobile'
                ? <Badge color="blue">Mobile</Badge>
                : <Badge color="grey">Web</Badge>;
            }
          },
          {
            id: 'last_execution_status',
            header: 'Last Status',
            sortingField: 'last_execution_status',
            width: 120,
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
            sortingField: 'last_execution_time',
            width: 120,
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
            sortingField: 'active',
            width: 100,
            cell: item => item.active ? (
              <Badge color="green">Active</Badge>
            ) : (
              <Badge color="red">Inactive</Badge>
            )
          }
        ]}
        sortingColumn={sortingColumn}
        sortingDescending={sortingDescending}
        onSortingChange={({ detail }) => {
          setSortingColumn(detail.sortingColumn);
          setSortingDescending(detail.isDescending ?? false);
        }}
        items={sortedUsecases}
        loading={loading}
        loadingText="Loading use cases..."
        empty={
          filteringText
            ? `No use cases match "${filteringText}"`
            : "No use cases found"
        }
        filter={
          <TextFilter
            filteringText={filteringText}
            onChange={({ detail }) => {
              const newSearchParams = new URLSearchParams(searchParams);
              if (detail.filteringText) {
                newSearchParams.set('search', detail.filteringText);
              } else {
                newSearchParams.delete('search');
              }
              setSearchParams(newSearchParams);
            }}
            filteringPlaceholder="Search use cases by name, description, tags, or status"
            countText={`${filteredUsecases.length} ${filteredUsecases.length === 1 ? 'match' : 'matches'}`}
          />
        }
        selectionType="multi"
        selectedItems={selectedItems}
        onSelectionChange={({ detail }) => setSelectedItems(detail.selectedItems)}
        resizableColumns
      />

      <DeleteUsecaseModal
        visible={showDeleteModal}
        usecaseCount={selectedItems.length}
        onDismiss={() => setShowDeleteModal(false)}
        onConfirm={handleBatchDelete}
        deleting={batchDeleting}
      />
    </SpaceBetween>
  );
}