import React from 'react';
import { useParams } from 'react-router-dom';
import { Box } from '@cloudscape-design/components';
import { usePermissions } from '../auth';
import { api } from '../utils/api';
import { AddItemsPicker } from './common/AddItemsPicker';
import { usecasePickerColumns, type PickerUsecase } from './common/usecasePickerColumns';
import { matchesUsecaseSearch } from './common/UsecasesTable';

interface ApplicationCandidate extends PickerUsecase {
  application_id?: string;
  owner_team_id?: string;
}

const AddUsecasesToApplication: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const { isAdmin, teams } = usePermissions();
  if (!id) {
    return <Box>Application ID not found</Box>;
  }

  const isInApplication = (item: ApplicationCandidate) => item.application_id === id;
  // Non-admins only see use cases owned by one of their teams.
  const userTeamIds = teams.map((t) => t.team_id);
  const isOwnedByUserTeam = (item: ApplicationCandidate) =>
    isAdmin || (!!item.owner_team_id && userTeamIds.includes(item.owner_team_id));

  return (
    <AddItemsPicker<ApplicationCandidate>
      key={id}
      backHref={`/applications/${id}`}
      breadcrumbs={(appName) => [
        { text: 'Home', href: '/' },
        { text: 'Applications', href: '/applications' },
        { text: appName || 'Loading...', href: `/applications/${id}` },
        { text: 'Add Use Cases' },
      ]}
      fetchTargetName={async () => (await api.get(`applications/${id}`))?.name}
      fetchCandidates={async () => (await api.get('usecases')).usecases || []}
      isCandidateVisible={isOwnedByUserTeam}
      columnDefinitions={usecasePickerColumns(isInApplication, 'Already in application')}
      getId={(item) => item.id}
      isAlreadyAdded={isInApplication}
      matchesSearch={matchesUsecaseSearch}
      onSubmit={async (selected) => {
        const usecaseIds = selected.map((item) => item.id);
        await api.post(`applications/${id}/usecases`, { usecase_ids: usecaseIds });
        return `Successfully added ${usecaseIds.length} use case(s) to the application`;
      }}
      labels={{
        title: 'Add Use Cases to Application',
        description: (appName) => `Select use cases to add to "${appName || 'this application'}"`,
        availableTitle: 'Available Use Cases',
        loadingText: 'Loading use cases...',
        filterPlaceholder: 'Search use cases by name, description, tags, or status',
        empty: 'No use cases found',
        noMatches: (text) => `No use cases match "${text}"`,
        targetLoadError: 'Failed to fetch application',
        candidatesLoadError: 'Failed to fetch use cases',
        submitError: 'Failed to add use cases to application',
      }}
    />
  );
};

export default AddUsecasesToApplication;
