import React from 'react';
import { useParams } from 'react-router-dom';
import { Box, type TableProps } from '@cloudscape-design/components';
import { api } from '../utils/api';
import { AddItemsPicker, PickerNameCell } from './common/AddItemsPicker';

interface TestSuiteItem {
  id: string;
  name: string;
  description?: string;
  application_id?: string;
  total_usecases?: number;
}

const matchesSuiteSearch = (suite: TestSuiteItem, searchText: string) =>
  Boolean(
    suite.name?.toLowerCase().includes(searchText) ||
    suite.description?.toLowerCase().includes(searchText)
  );

const AddTestSuitesToApplication: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  if (!id) {
    return <Box>Application ID not found</Box>;
  }

  const isInApplication = (suite: TestSuiteItem) => suite.application_id === id;
  const columns: TableProps.ColumnDefinition<TestSuiteItem>[] = [
    {
      id: 'name',
      header: 'Name',
      cell: (item) => (
        <PickerNameCell
          name={item.name}
          href={`/test-suites/${item.id}`}
          description={item.description}
          alreadyAddedLabel={isInApplication(item) ? 'Already in application' : undefined}
        />
      ),
    },
    {
      id: 'usecases',
      header: 'Usecases',
      width: 100,
      cell: (item) => item.total_usecases ?? '-',
    },
  ];

  return (
    <AddItemsPicker<TestSuiteItem>
      key={id}
      backHref={`/applications/${id}`}
      breadcrumbs={(appName) => [
        { text: 'Home', href: '/' },
        { text: 'Applications', href: '/applications' },
        { text: appName || 'Loading...', href: `/applications/${id}` },
        { text: 'Add Test Suites' },
      ]}
      fetchTargetName={async () => (await api.get(`applications/${id}`))?.name}
      fetchCandidates={async () => (await api.get('test-suites')).suites || []}
      columnDefinitions={columns}
      getId={(item) => item.id}
      isAlreadyAdded={isInApplication}
      matchesSearch={matchesSuiteSearch}
      onSubmit={async (selected) => {
        // No batch endpoint: associate each suite with its own PUT.
        await Promise.all(selected.map((suite) => api.put(`test-suites/${suite.id}`, { application_id: id })));
        return `Successfully associated ${selected.length} test suite(s) with the application`;
      }}
      labels={{
        title: 'Add Test Suites to Application',
        description: (appName) => `Select test suites to associate with "${appName || 'this application'}"`,
        availableTitle: 'Available Test Suites',
        loadingText: 'Loading test suites...',
        filterPlaceholder: 'Search test suites by name or description',
        empty: 'No test suites found',
        noMatches: (text) => `No test suites match "${text}"`,
        targetLoadError: 'Failed to fetch application',
        candidatesLoadError: 'Failed to fetch test suites',
        submitError: 'Failed to associate test suites',
      }}
    />
  );
};

export default AddTestSuitesToApplication;
