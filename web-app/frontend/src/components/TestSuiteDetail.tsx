import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  SpaceBetween,
  Container,
  Header,
  Button,
  ButtonDropdown,
  Table,
  Box,
  Modal,
  Alert,
  StatusIndicator,
  Link,
  Badge,
  KeyValuePairs,
  CopyToClipboard
} from '@cloudscape-design/components';
import { testSuites, TestSuite, SuiteExecution } from '../utils/api';
import { ErrorState } from '../utils/errorManager';
import { ContainerLoading, HeaderLoading } from './common/LoadingStates';
import Breadcrumb from './common/Breadcrumb';

interface UseCase {
  usecase_id: string;
  usecase_name: string;
  added_at: string;
}

const TestSuiteDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  // State for suite data
  const [suite, setSuite] = useState<TestSuite | null>(null);
  const [usecases, setUsecases] = useState<UseCase[]>([]);
  const [executions, setExecutions] = useState<SuiteExecution[]>([]);

  // Loading states
  const [loadingSuite, setLoadingSuite] = useState(true);
  const [loadingUsecases, setLoadingUsecases] = useState(true);
  const [loadingExecutions, setLoadingExecutions] = useState(true);

  // Action states
  const [executing, setExecuting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [removingUsecase, setRemovingUsecase] = useState(false);

  // Modal states
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showRemoveUsecaseModal, setShowRemoveUsecaseModal] = useState(false);
  const [usecaseToRemove, setUsecaseToRemove] = useState<UseCase | null>(null);

  // Selection states
  const [selectedUsecases, setSelectedUsecases] = useState<UseCase[]>([]);

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

  // Fetch use cases
  const fetchUsecases = async () => {
    if (!id) return;
    try {
      setLoadingUsecases(true);
      const data = await testSuites.listUsecases(id);
      setUsecases(data.usecases || []);
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to fetch use cases');
    } finally {
      setLoadingUsecases(false);
    }
  };

  // Fetch recent executions
  const fetchExecutions = async () => {
    if (!id) return;
    try {
      setLoadingExecutions(true);
      const data = await testSuites.listExecutions(id, { limit: 10 });
      setExecutions(data.executions || []);
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to fetch executions');
    } finally {
      setLoadingExecutions(false);
    }
  };

  // Execute suite
  const handleExecute = async () => {
    if (!id) return;
    try {
      setExecuting(true);
      await testSuites.execute(id);
      setSuccess('Suite execution started successfully');
      fetchExecutions();
      fetchSuite();
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to execute test suite');
    } finally {
      setExecuting(false);
    }
  };

  // Delete suite
  const handleDelete = async () => {
    if (!id) return;
    try {
      setDeleting(true);
      await testSuites.delete(id);
      navigate('/test-suites');
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to delete test suite');
    } finally {
      setDeleting(false);
      setShowDeleteModal(false);
    }
  };

  // Remove use case from suite
  const handleRemoveUsecase = async () => {
    if (!usecaseToRemove) return;

    try {
      setRemovingUsecase(true);
      await testSuites.removeUsecase(id!, usecaseToRemove.usecase_id);
      setSuccess(`Removed "${usecaseToRemove.usecase_name}" from suite`);
      setUsecaseToRemove(null);
      setShowRemoveUsecaseModal(false);
      fetchUsecases();
      fetchSuite();
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to remove use case');
    } finally {
      setRemovingUsecase(false);
    }
  };

  // Get status indicator for execution
  const getExecutionStatus = (status: string) => {
    switch (status) {
      case 'completed':
        return <StatusIndicator type="success">Completed</StatusIndicator>;
      case 'partial':
        return <StatusIndicator type="warning">Partial</StatusIndicator>;
      case 'failed':
        return <StatusIndicator type="error">Failed</StatusIndicator>;
      case 'running':
        return <StatusIndicator type="in-progress">Running</StatusIndicator>;
      case 'pending':
        return <StatusIndicator type="pending">Pending</StatusIndicator>;
      default:
        return <StatusIndicator type="info">{status}</StatusIndicator>;
    }
  };

  // Format date
  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  // Format duration
  const formatDuration = (seconds?: number): string => {
    if (!seconds) return 'N/A';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  };

  // Initial data fetch
  useEffect(() => {
    if (!id) return;
    fetchSuite();
    fetchUsecases();
    fetchExecutions();
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

  return (
    <SpaceBetween direction="vertical" size="l">
      {/* Breadcrumb */}
      <Breadcrumb
        items={[
          { text: 'Home', href: '/' },
          { text: 'Test Suites', href: '/test-suites' },
          { text: suite?.name || 'Loading...' }
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

      {/* Suite Header */}
      {loadingSuite ? (
        <HeaderLoading variant="h1" text="Loading test suite..." />
      ) : suite ? (
        <Header
          variant="h1"
          description={suite.description}
          actions={
            <SpaceBetween direction="horizontal" size="xs">
              <Button
                onClick={fetchSuite}
                iconName="refresh"
                variant="icon"
                ariaLabel="Refresh"
              />
              <Button
                variant="primary"
                loading={executing}
                disabled={executing || !suite || suite.total_usecases === 0}
                onClick={handleExecute}
              >
                {executing ? 'Executing...' : 'Execute Suite'}
              </Button>
              <ButtonDropdown
                onItemClick={({ detail }) => {
                  switch (detail.id) {
                    case 'configure-schedule':
                      navigate(`/test-suites/${id}/schedule`);
                      break;
                    case 'edit':
                      navigate(`/test-suites/${id}/edit`);
                      break;
                    case 'delete':
                      setShowDeleteModal(true);
                      break;
                  }
                }}
                items={[
                  {
                    id: 'configure-schedule',
                    text: 'Configure Schedule',
                    iconName: 'calendar'
                  },
                  {
                    id: 'edit',
                    text: 'Edit',
                    iconName: 'edit'
                  },
                  {
                    id: 'delete',
                    text: 'Delete',
                    iconName: 'remove'
                  }
                ]}
              >
                Actions
              </ButtonDropdown>
            </SpaceBetween>
          }
        >
          {suite.name}
        </Header>
      ) : (
        <Box>Suite not found</Box>
      )}

      {/* Suite Info */}
      {suite && (
        <Container
          header={
            <Header variant="h2">
              Test Suite Information
            </Header>
          }
        >
          <KeyValuePairs
            columns={3}
            items={[
              {
                label: "Suite ID",
                value: (
                  <CopyToClipboard
                    copyButtonAriaLabel="Copy Suite ID"
                    copyErrorText="Failed to copy"
                    copySuccessText="Suite ID copied"
                    textToCopy={id}
                    variant="inline"
                  />
                ),
              },
              {
                label: "Name",
                value: suite.name,
              },
              {
                label: "Description",
                value: suite.description || 'No description',
              },
              {
                label: "Total Use Cases",
                value: suite.total_usecases || 0,
              },
              {
                label: "Last Execution",
                value: suite.last_execution_status ? (
                  getExecutionStatus(suite.last_execution_status)
                ) : (
                  'Never run'
                ),
              },
              {
                label: "Success Rate",
                value: suite.last_successful_count && suite.total_usecases
                  ? `${Math.round((suite.last_successful_count / suite.total_usecases) * 100)}%`
                  : 'N/A',
              },
              {
                label: "Created",
                value: suite.created_at ? new Date(suite.created_at).toLocaleDateString() : 'N/A',
              },
              {
                label: "Tags",
                value: suite.tags && suite.tags.length > 0 ? (
                  <SpaceBetween direction="horizontal" size="xxs">
                    {suite.tags.map((tag) => (
                      <Badge key={tag}>{tag}</Badge>
                    ))}
                  </SpaceBetween>
                ) : (
                  'No tags'
                ),
              },
            ]}
          />
        </Container>
      )}

      {/* Use Cases Table */}
      {loadingUsecases ? (
        <ContainerLoading title="Use Cases" text="Loading use cases..." />
      ) : (
        <Table
          header={
            <Header
              variant="h2"
              counter={`(${usecases.length})`}
              actions={
                <SpaceBetween direction="horizontal" size="xs">
                  <Button
                    onClick={() => navigate(`/test-suites/${id}/add-usecases`)}
                    iconName="add-plus"
                  >
                    Add Use Cases
                  </Button>
                  <Button
                    onClick={fetchUsecases}
                    iconName="refresh"
                    variant="icon"
                    ariaLabel="Refresh use cases"
                  />
                </SpaceBetween>
              }
            >
              Use Cases
            </Header>
          }
          columnDefinitions={[
              {
                id: 'name',
                header: 'Name',
                cell: (item: UseCase) => (
                  <Link href={`/usecase/${item.usecase_id}`}>
                    {item.usecase_name}
                  </Link>
                ),
                sortingField: 'usecase_name',
                width: 300
              },
              {
                id: 'added_at',
                header: 'Added',
                cell: (item: UseCase) => formatDate(item.added_at),
                sortingField: 'added_at',
                width: 200
              },
              {
                id: 'actions',
                header: 'Actions',
                cell: (item: UseCase) => (
                  <Button
                    variant="icon"
                    iconName="remove"
                    onClick={() => {
                      setUsecaseToRemove(item);
                      setShowRemoveUsecaseModal(true);
                    }}
                    ariaLabel={`Remove ${item.usecase_name}`}
                  />
                ),
                width: 100
              }
            ]}
            items={usecases}
            selectionType="multi"
            selectedItems={selectedUsecases}
            onSelectionChange={({ detail }) => setSelectedUsecases(detail.selectedItems)}
            empty={
              <Box textAlign="center" color="inherit">
                <b>No use cases</b>
                <Box padding={{ bottom: 's' }} variant="p" color="inherit">
                  No use cases have been added to this suite yet.
                </Box>
                <Button onClick={() => navigate(`/test-suites/${id}/add-usecases`)}>
                  Add Use Cases
                </Button>
              </Box>
            }
          />
      )}

      {/* Recent Executions Table */}
      {loadingExecutions ? (
        <ContainerLoading title="Recent Executions" text="Loading executions..." />
      ) : (
        <Table
          header={
            <Header
              variant="h2"
              counter={`(${executions.length})`}
              actions={
                <Button
                  onClick={fetchExecutions}
                  iconName="refresh"
                  variant="icon"
                  ariaLabel="Refresh executions"
                />
              }
            >
              Recent Executions
            </Header>
          }
          columnDefinitions={[
              {
                id: 'id',
                header: 'Execution ID',
                cell: (item: SuiteExecution) => (
                  <Link href={`/test-suites/${id}/executions/${item.id}`}>
                    {item.id.substring(0, 8)}...
                  </Link>
                )
              },
              {
                id: 'status',
                header: 'Status',
                cell: (item: SuiteExecution) => getExecutionStatus(item.status)
              },
              {
                id: 'progress',
                header: 'Progress',
                cell: (item: SuiteExecution) => (
                  <Box>
                    {item.completed_usecases}/{item.total_usecases} completed
                    {item.successful_usecases > 0 && (
                      <Box fontSize="body-s" color="text-status-success">
                        {item.successful_usecases} passed
                      </Box>
                    )}
                    {item.failed_usecases > 0 && (
                      <Box fontSize="body-s" color="text-status-error">
                        {item.failed_usecases} failed
                      </Box>
                    )}
                  </Box>
                )
              },
              {
                id: 'started_at',
                header: 'Started',
                cell: (item: SuiteExecution) => formatDate(item.started_at),
                sortingField: 'started_at'
              },
              {
                id: 'duration',
                header: 'Duration',
                cell: (item: SuiteExecution) => formatDuration(item.duration_seconds)
              },
              {
                id: 'trigger',
                header: 'Trigger',
                cell: (item: SuiteExecution) => (
                  <Badge color={item.trigger_type === 'scheduled' ? 'green' : 'blue'}>
                    {item.trigger_type}
                  </Badge>
                )
              }
            ]}
            items={executions}
            sortingDisabled={false}
            empty={
              <Box textAlign="center" color="inherit">
                <b>No executions</b>
                <Box padding={{ bottom: 's' }} variant="p" color="inherit">
                  This suite has not been executed yet.
                </Box>
                <Button
                  variant="primary"
                  onClick={handleExecute}
                  disabled={!suite || suite.total_usecases === 0}
                >
                  Execute Suite
                </Button>
              </Box>
            }
          />
      )}

      {/* Delete Suite Modal */}
      <Modal
        onDismiss={() => !deleting && setShowDeleteModal(false)}
        visible={showDeleteModal}
        closeAriaLabel="Close modal"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button
                variant="link"
                onClick={() => setShowDeleteModal(false)}
                disabled={deleting}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleDelete}
                loading={deleting}
                disabled={deleting}
              >
                Delete
              </Button>
            </SpaceBetween>
          </Box>
        }
        header="Delete Test Suite"
      >
        <SpaceBetween direction="vertical" size="m">
          <Box variant="span">
            Are you sure you want to delete the test suite{' '}
            <Box variant="span" fontWeight="bold">
              {suite?.name}
            </Box>
            ? This action cannot be undone.
          </Box>
          <Box variant="span">
            All use case mappings and execution history will be permanently removed.
          </Box>
        </SpaceBetween>
      </Modal>

      {/* Remove Use Case Modal */}
      <Modal
        onDismiss={() => !removingUsecase && setShowRemoveUsecaseModal(false)}
        visible={showRemoveUsecaseModal}
        closeAriaLabel="Close modal"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button
                variant="link"
                onClick={() => setShowRemoveUsecaseModal(false)}
                disabled={removingUsecase}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleRemoveUsecase}
                loading={removingUsecase}
                disabled={removingUsecase}
              >
                Remove
              </Button>
            </SpaceBetween>
          </Box>
        }
        header="Remove Use Case"
      >
        <Box variant="span">
          Are you sure you want to remove{' '}
          <Box variant="span" fontWeight="bold">
            {usecaseToRemove?.usecase_name}
          </Box>
          {' '}from this test suite?
        </Box>
      </Modal>
    </SpaceBetween>
  );
};

export default TestSuiteDetail;
