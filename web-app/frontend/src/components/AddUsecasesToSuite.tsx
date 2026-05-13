import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  SpaceBetween,
  Header,
  Button,
  Table,
  Box,
  Alert,
  Badge,
  TextFilter,
  StatusIndicator,
  Link
} from '@cloudscape-design/components';
import { testSuites, api } from '../utils/api';
import { ErrorState } from '../utils/errorManager';
import { ContainerLoading } from './common/LoadingStates';
import Breadcrumb from './common/Breadcrumb';

interface Usecase {
  id: string;
  name: string;
  description: string;
  tags?: string[];
  scope?: string;
  active: boolean;
  last_execution_id?: string;
  last_execution_status?: string;
  last_execution_time?: string;
}

interface UsecaseInSuite {
  usecase_id: string;
  usecase_name: string;
  usecase_scope: string;
}

// Helper function to format time ago (same as HomeScreen)
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

// Helper function to get status type for StatusIndicator (same as HomeScreen)
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

const AddUsecasesToSuite: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  // State for data
  const [suite, setSuite] = useState<any>(null);
  const [allUsecases, setAllUsecases] = useState<Usecase[]>([]);
  const [usecasesInSuite, setUsecasesInSuite] = useState<UsecaseInSuite[]>([]);

  // Loading states
  const [loadingSuite, setLoadingSuite] = useState(true);
  const [loadingUsecases, setLoadingUsecases] = useState(true);
  const [adding, setAdding] = useState(false);

  // Selection and filter states
  const [selectedItems, setSelectedItems] = useState<Usecase[]>([]);
  const [filteringText, setFilteringText] = useState('');

  // Alert states
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Fetch suite details
  const fetchSuite = async () => {
    if (!id) return;
    try {
      setLoadingSuite(true);
      const data = await testSuites.get(id);
      setSuite(data);
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to fetch test suite');
    } finally {
      setLoadingSuite(false);
    }
  };

  // Fetch all available use cases
  const fetchAllUsecases = async () => {
    try {
      setLoadingUsecases(true);
      const data = await api.get('usecases');
      setAllUsecases(data.usecases || []);
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to fetch use cases');
    } finally {
      setLoadingUsecases(false);
    }
  };

  // Fetch use cases already in suite
  const fetchUsecasesInSuite = async () => {
    if (!id) return;
    try {
      const data = await testSuites.listUsecases(id);
      setUsecasesInSuite(data.usecases || []);
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to fetch suite use cases');
    }
  };

  // Add selected use cases to suite
  const handleAddUsecases = async () => {
    if (selectedItems.length === 0) {
      setError('Please select at least one use case to add');
      return;
    }

    try {
      setAdding(true);
      const usecaseIds = selectedItems.map(item => item.id);
      const result = await testSuites.addUsecases(id!, { usecase_ids: usecaseIds });
      
      setSuccess(`Successfully added ${result.added} use case(s) to the suite`);
      
      // Navigate back to suite detail after a short delay
      setTimeout(() => {
        navigate(`/test-suites/${id}`);
      }, 1500);
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to add use cases to suite');
    } finally {
      setAdding(false);
    }
  };

  // Check if a use case is already in the suite
  const isUsecaseInSuite = (usecaseId: string): boolean => {
    return usecasesInSuite.some(uc => uc.usecase_id === usecaseId);
  };

  // Filter use cases based on search text (same as HomeScreen)
  const getFilteredUsecases = (): Usecase[] => {
    return allUsecases.filter(usecase => {
      if (!filteringText) return true;
      
      const searchText = filteringText.toLowerCase();
      const nameMatch = usecase.name?.toLowerCase().includes(searchText) || false;
      const descriptionMatch = usecase.description?.toLowerCase().includes(searchText) || false;
      const tagsMatch = usecase.tags?.some(tag => tag?.toLowerCase().includes(searchText)) || false;
      const statusMatch = usecase.last_execution_status?.toLowerCase().includes(searchText) || false;
      
      return nameMatch || descriptionMatch || tagsMatch || statusMatch;
    });
  };

  // Initial data fetch
  useEffect(() => {
    if (!id) return;
    fetchSuite();
    fetchAllUsecases();
    fetchUsecasesInSuite();
  }, [id]);

  // Auto-dismiss alerts
  useEffect(() => {
    if (error || success) {
      const timer = setTimeout(() => {
        setError(null);
        setSuccess(null);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [error, success]);

  if (!id) {
    return <Box>Suite ID not found</Box>;
  }

  const filteredUsecases = getFilteredUsecases();

  return (
    <SpaceBetween direction="vertical" size="l">
      {/* Breadcrumb */}
      <Breadcrumb
        items={[
          { text: 'Home', href: '/' },
          { text: 'Test Suites', href: '/test-suites' },
          { text: suite?.name || 'Loading...', href: `/test-suites/${id}` },
          { text: 'Add Use Cases' }
        ]}
      />

      {/* Alerts */}
      {error && (
        <Alert type="error" dismissible onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert type="success" dismissible onDismiss={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      {/* Header */}
      <Header
        variant="h1"
        description={`Select use cases to add to "${suite?.name || 'this suite'}"`}
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            <Button
              onClick={() => navigate(`/test-suites/${id}`)}
              disabled={adding}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleAddUsecases}
              loading={adding}
              disabled={adding || selectedItems.length === 0}
            >
              Add Selected ({selectedItems.length})
            </Button>
          </SpaceBetween>
        }
      >
        Add Use Cases to Suite
      </Header>

      {/* Use Cases Table */}
      {loadingUsecases || loadingSuite ? (
        <ContainerLoading title="Available Use Cases" text="Loading use cases..." />
      ) : (
        <Table
          columnDefinitions={[
            { 
              id: 'name', 
              header: 'Name',
              minWidth: 450,
              cell: item => (
                <div>
                  <Link href={`/usecase/${item.id}`} external>
                    {item.name}
                  </Link>
                  {item.description && (
                    <div style={{ fontSize: '0.85em', color: '#5f6b7a', marginTop: '4px', whiteSpace: 'pre-line' }}>
                      {item.description}
                    </div>
                  )}
                  {isUsecaseInSuite(item.id) && (
                    <div style={{ marginTop: '4px' }}>
                      <Badge color="green">Already in suite</Badge>
                    </div>
                  )}
                </div>
              )
            },
            { 
              id: 'last_execution_status', 
              header: 'Last Status', 
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
              width: 100, 
              cell: item => item.active ? (
                <Badge color="green">Active</Badge>
              ) : (
                <Badge color="red">Inactive</Badge>
              )
            }
          ]}
          items={filteredUsecases}
          loading={loadingUsecases || loadingSuite}
          loadingText="Loading use cases..."
          empty={
            filteringText 
              ? `No use cases match "${filteringText}"`
              : "No use cases found"
          }
          filter={
            <TextFilter
              filteringText={filteringText}
              onChange={({ detail }) => setFilteringText(detail.filteringText)}
              filteringPlaceholder="Search use cases by name, description, tags, or status"
              countText={`${filteredUsecases.length} ${filteredUsecases.length === 1 ? 'match' : 'matches'}`}
            />
          }
          selectionType="multi"
          selectedItems={selectedItems}
          onSelectionChange={({ detail }) => setSelectedItems(detail.selectedItems)}
          isItemDisabled={(item: Usecase) => isUsecaseInSuite(item.id)}
          resizableColumns
        />
      )}
    </SpaceBetween>
  );
};

export default AddUsecasesToSuite;
