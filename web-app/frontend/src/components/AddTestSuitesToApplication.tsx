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
  Link
} from '@cloudscape-design/components';
import { api } from '../utils/api';
import { ErrorState } from '../utils/errorManager';
import { ContainerLoading } from './common/LoadingStates';
import Breadcrumb from './common/Breadcrumb';

interface TestSuiteItem {
  id: string;
  name: string;
  description: string;
  application_id?: string;
  total_usecases?: number;
}

const AddTestSuitesToApplication: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [application, setApplication] = useState<any>(null);
  const [allSuites, setAllSuites] = useState<TestSuiteItem[]>([]);
  const [loadingApp, setLoadingApp] = useState(true);
  const [loadingSuites, setLoadingSuites] = useState(true);
  const [adding, setAdding] = useState(false);
  const [selectedItems, setSelectedItems] = useState<TestSuiteItem[]>([]);
  const [filteringText, setFilteringText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const fetchApplication = async () => {
    if (!id) return;
    try {
      setLoadingApp(true);
      const data = await api.get(`applications/${id}`);
      setApplication(data);
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to fetch application');
    } finally {
      setLoadingApp(false);
    }
  };

  const fetchAllSuites = async () => {
    try {
      setLoadingSuites(true);
      const data = await api.get('test-suites');
      setAllSuites(data.suites || []);
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to fetch test suites');
    } finally {
      setLoadingSuites(false);
    }
  };

  const handleAddSuites = async () => {
    if (selectedItems.length === 0) {
      setError('Please select at least one test suite to add');
      return;
    }

    try {
      setAdding(true);
      await Promise.all(
        selectedItems.map(suite =>
          api.put(`test-suites/${suite.id}`, { application_id: id })
        )
      );

      setSuccess(`Successfully associated ${selectedItems.length} test suite(s) with the application`);

      setTimeout(() => {
        navigate(`/applications/${id}`);
      }, 1500);
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to associate test suites');
    } finally {
      setAdding(false);
    }
  };

  const isAlreadyInApplication = (suite: TestSuiteItem): boolean => {
    return suite.application_id === id;
  };

  const getFilteredSuites = (): TestSuiteItem[] => {
    return allSuites.filter(suite => {
      if (!filteringText) return true;
      const searchText = filteringText.toLowerCase();
      return (
        suite.name?.toLowerCase().includes(searchText) ||
        suite.description?.toLowerCase().includes(searchText)
      );
    });
  };

  useEffect(() => {
    if (!id) return;
    fetchApplication();
    fetchAllSuites();
  }, [id]);

  useEffect(() => {
    if (error || success) {
      const timer = setTimeout(() => { setError(null); setSuccess(null); }, 5000);
      return () => clearTimeout(timer);
    }
  }, [error, success]);

  if (!id) {
    return <Box>Application ID not found</Box>;
  }

  const filteredSuites = getFilteredSuites();

  return (
    <SpaceBetween direction="vertical" size="l">
      <Breadcrumb
        items={[
          { text: 'Home', href: '/' },
          { text: 'Applications', href: '/applications' },
          { text: application?.name || 'Loading...', href: `/applications/${id}` },
          { text: 'Add Test Suites' }
        ]}
      />

      {error && (
        <Alert type="error" dismissible onDismiss={() => setError(null)}>{error}</Alert>
      )}

      {success && (
        <Alert type="success" dismissible onDismiss={() => setSuccess(null)}>{success}</Alert>
      )}

      <Header
        variant="h1"
        description={`Select test suites to associate with "${application?.name || 'this application'}"`}
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            <Button onClick={() => navigate(`/applications/${id}`)} disabled={adding}>Cancel</Button>
            <Button
              variant="primary"
              onClick={handleAddSuites}
              loading={adding}
              disabled={adding || selectedItems.length === 0}
            >
              Add Selected ({selectedItems.length})
            </Button>
          </SpaceBetween>
        }
      >
        Add Test Suites to Application
      </Header>

      {loadingSuites || loadingApp ? (
        <ContainerLoading title="Available Test Suites" text="Loading test suites..." />
      ) : (
        <Table
          items={filteredSuites}
          trackBy="id"
          selectionType="multi"
          selectedItems={selectedItems}
          onSelectionChange={({ detail }) => setSelectedItems(detail.selectedItems)}
          isItemDisabled={(item: TestSuiteItem) => isAlreadyInApplication(item)}
          columnDefinitions={[
            {
              id: 'name',
              header: 'Name',
              cell: item => (
                <div>
                  <Link href={`/test-suites/${item.id}`} external>{item.name}</Link>
                  {item.description && (
                    <div style={{ fontSize: '0.85em', color: '#5f6b7a', marginTop: '4px' }}>
                      {item.description}
                    </div>
                  )}
                  {isAlreadyInApplication(item) && (
                    <div style={{ marginTop: '4px' }}>
                      <Badge color="green">Already in application</Badge>
                    </div>
                  )}
                </div>
              )
            },
            {
              id: 'usecases',
              header: 'Usecases',
              width: 100,
              cell: item => item.total_usecases ?? '-',
            },
          ]}
          filter={
            <TextFilter
              filteringText={filteringText}
              onChange={({ detail }) => setFilteringText(detail.filteringText)}
              filteringPlaceholder="Search test suites by name or description"
              countText={`${filteredSuites.length} ${filteredSuites.length === 1 ? 'match' : 'matches'}`}
            />
          }
          empty={
            filteringText
              ? `No test suites match "${filteringText}"`
              : "No test suites found"
          }
          resizableColumns
        />
      )}
    </SpaceBetween>
  );
};

export default AddTestSuitesToApplication;
