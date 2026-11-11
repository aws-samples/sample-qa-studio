import React from 'react';
import { useParams } from 'react-router-dom';
import { Box } from '@cloudscape-design/components';
import { testSuites, api } from '../utils/api';
import { AddItemsPicker } from './common/AddItemsPicker';
import { usecasePickerColumns, type PickerUsecase } from './common/usecasePickerColumns';
import { matchesUsecaseSearch } from './common/UsecasesTable';

/** A use case plus whether the suite already contains it. */
interface SuiteCandidate extends PickerUsecase {
  inSuite: boolean;
}

const isInSuite = (item: SuiteCandidate) => item.inSuite;
const columns = usecasePickerColumns<SuiteCandidate>(isInSuite, 'Already in suite');

const AddUsecasesToSuite: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  if (!id) {
    return <Box>Suite ID not found</Box>;
  }

  return (
    <AddItemsPicker<SuiteCandidate>
      key={id}
      backHref={`/test-suites/${id}`}
      breadcrumbs={(suiteName) => [
        { text: 'Home', href: '/' },
        { text: 'Test Suites', href: '/test-suites' },
        { text: suiteName || 'Loading...', href: `/test-suites/${id}` },
        { text: 'Add Use Cases' },
      ]}
      fetchTargetName={async () => (await testSuites.get(id))?.name}
      fetchCandidates={async () => {
        const [all, inSuite] = await Promise.all([api.get('usecases'), testSuites.listUsecases(id)]);
        const inSuiteIds = new Set((inSuite.usecases || []).map((uc: { usecase_id: string }) => uc.usecase_id));
        return ((all.usecases || []) as PickerUsecase[]).map((uc) => ({ ...uc, inSuite: inSuiteIds.has(uc.id) }));
      }}
      columnDefinitions={columns}
      getId={(item) => item.id}
      isAlreadyAdded={isInSuite}
      matchesSearch={matchesUsecaseSearch}
      onSubmit={async (selected) => {
        const result = await testSuites.addUsecases(id, { usecase_ids: selected.map((item) => item.id) });
        return `Successfully added ${result.added} use case(s) to the suite`;
      }}
      labels={{
        title: 'Add Use Cases to Suite',
        description: (suiteName) => `Select use cases to add to "${suiteName || 'this suite'}"`,
        availableTitle: 'Available Use Cases',
        loadingText: 'Loading use cases...',
        filterPlaceholder: 'Search use cases by name, description, tags, or status',
        empty: 'No use cases found',
        noMatches: (text) => `No use cases match "${text}"`,
        targetLoadError: 'Failed to fetch test suite',
        candidatesLoadError: 'Failed to fetch use cases',
        submitError: 'Failed to add use cases to suite',
      }}
    />
  );
};

export default AddUsecasesToSuite;
