import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Container,
  Header,
  SpaceBetween,
  Button,
  Table,
  Box,
  Alert,
  StatusIndicator,
  TextFilter,
  Badge,
  Link
} from '@cloudscape-design/components';
import { testSuites, TestSuite } from '../utils/api';
import { ErrorState } from '../utils/errorManager';

const TestSuites: React.FC = () => {
  const [suites, setSuites] = useState<TestSuite[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [filteringText, setFilteringText] = useState('');
  const [selectedItems, setSelectedItems] = useState<TestSuite[]>([]);

  const navigate = useNavigate();

  const fetchSuites = async () => {
    try {
      setLoading(true);
      const data = await testSuites.list();
      setSuites(data.suites || []);
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to fetch test suites');
    } finally {
      setLoading(false);
    }
  };

  const getStatusIndicator = (suite: TestSuite) => {
    if (!suite.last_execution_status) {
      return <StatusIndicator type="stopped">Never run</StatusIndicator>;
    }

    switch (suite.last_execution_status) {
      case 'completed':
        return <StatusIndicator type="success">Completed</StatusIndicator>;
      case 'partial':
        return <StatusIndicator type="warning">Partial</StatusIndicator>;
      case 'failed':
        return <StatusIndicator type="error">Failed</StatusIndicator>;
      default:
        return <StatusIndicator type="info">{suite.last_execution_status}</StatusIndicator>;
    }
  };

  const formatLastRun = (time?: string): string => {
    if (!time) return 'Never';
    const date = new Date(time);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  // Filter suites based on search text
  const filteredSuites = suites.filter(suite => {
    if (!filteringText) return true;
    
    const searchText = filteringText.toLowerCase();
    const nameMatch = suite.name?.toLowerCase().includes(searchText) || false;
    const descriptionMatch = suite.description?.toLowerCase().includes(searchText) || false;
    const tagsMatch = suite.tags?.some(tag => tag?.toLowerCase().includes(searchText)) || false;
    
    return nameMatch || descriptionMatch || tagsMatch;
  });

  useEffect(() => {
    fetchSuites();
  }, []);

  useEffect(() => {
    if (error || success) {
      const timer = setTimeout(() => {
        setError(null);
        setSuccess(null);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [error, success]);

  return (
    <SpaceBetween direction="vertical" size="l">
      <Header
        variant="h1"
        description="Manage and execute test suites to run multiple use cases together."
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            <Button
              onClick={fetchSuites}
              iconName="refresh"
              variant="icon"
            />
            <Button
              variant="primary"
              onClick={() => navigate('/test-suites/create')}
            >
              Create Test Suite
            </Button>
          </SpaceBetween>
        }
      >
        Test Suites
      </Header>

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

      <Container>
        <Table
          variant="embedded"
          selectionType="multi"
          selectedItems={selectedItems}
          onSelectionChange={({ detail }) => setSelectedItems(detail.selectedItems)}
          columnDefinitions={[
            {
              id: 'name',
              header: 'Name',
              cell: (suite: TestSuite) => (
                <div>
                  <div style={{ fontWeight: 500 }}>
                    <Link
                      onFollow={(e) => {
                        e.preventDefault();
                        navigate(`/test-suites/${suite.id}`);
                      }}
                      href={`/test-suites/${suite.id}`}
                    >
                      {suite.name}
                    </Link>
                  </div>
                  {suite.description && (
                    <div style={{ fontSize: '0.85em', color: '#5f6b7a', marginTop: '4px' }}>
                      {suite.description}
                    </div>
                  )}
                </div>
              ),
              sortingField: 'name',
              minWidth: 200
            },
            {
              id: 'tags',
              header: 'Tags',
              cell: (suite: TestSuite) => {
                if (!suite.tags || suite.tags.length === 0) {
                  return <Box color="text-status-inactive">No tags</Box>;
                }
                return (
                  <SpaceBetween direction="horizontal" size="xxs">
                    {suite.tags.slice(0, 3).map((tag) => (
                      <Badge key={tag}>{tag}</Badge>
                    ))}
                    {suite.tags.length > 3 && (
                      <Badge>+{suite.tags.length - 3}</Badge>
                    )}
                  </SpaceBetween>
                );
              },
              width: 180
            },
            {
              id: 'total_tests',
              header: 'Total Tests',
              cell: (suite: TestSuite) => suite.total_usecases || 0,
              sortingField: 'total_usecases',
              width: 100
            },
            {
              id: 'last_run',
              header: 'Last Run',
              cell: (suite: TestSuite) => formatLastRun(suite.last_execution_time),
              sortingField: 'last_execution_time',
              width: 120
            },
            {
              id: 'status',
              header: 'Status',
              cell: (suite: TestSuite) => getStatusIndicator(suite),
              width: 120
            }
          ]}
          items={filteredSuites}
          loading={loading}
          loadingText="Loading test suites..."
          filter={
            <TextFilter
              filteringText={filteringText}
              onChange={({ detail }) => setFilteringText(detail.filteringText)}
              filteringPlaceholder="Search by name, description, or tags"
              countText={`${filteredSuites.length} ${filteredSuites.length === 1 ? 'match' : 'matches'}`}
            />
          }
          empty={
            <Box textAlign="center" color="inherit">
              <b>No test suites found</b>
              <Box padding={{ bottom: 's' }} variant="p" color="inherit">
                No test suites to display.
              </Box>
              <Button onClick={() => navigate('/test-suites/create')}>
                Create Test Suite
              </Button>
            </Box>
          }
        />
      </Container>
    </SpaceBetween>
  );
};

export default TestSuites;
