import React, { useState } from 'react';
import Box from '@cloudscape-design/components/box';
import FormField from '@cloudscape-design/components/form-field';
import Select, { SelectProps } from '@cloudscape-design/components/select';
import { AccessLevel, Team } from '../../types/permissions';
import FormModal from '../common/FormModal';

interface GrantAccessModalProps {
  visible: boolean;
  onDismiss: () => void;
  onSubmit: (targetTeamId: string, appId: string, level: AccessLevel) => Promise<void>;
  /** All teams except the current one */
  availableTeams: Team[];
  /** Applications available for sharing */
  availableApps: Array<{ id: string; name: string }>;
}

const ACCESS_LEVEL_OPTIONS: SelectProps.Option[] = [
  { label: 'View', value: 'view', description: 'Can view the application and results' },
  { label: 'Execute', value: 'execute', description: 'Can view and execute test cases' },
  { label: 'Full', value: 'full', description: 'Full edit access (subject to ceiling rule)' },
];

const GrantAccessModal: React.FC<GrantAccessModalProps> = ({
  visible,
  onDismiss,
  onSubmit,
  availableTeams,
  availableApps,
}) => {
  const [selectedTeam, setSelectedTeam] = useState<SelectProps.Option | null>(null);
  const [selectedApp, setSelectedApp] = useState<SelectProps.Option | null>(null);
  const [selectedLevel, setSelectedLevel] = useState<SelectProps.Option | null>(null);

  const teamOptions: SelectProps.Option[] = availableTeams.map((t) => ({
    label: t.name,
    value: t.id,
  }));

  const appOptions: SelectProps.Option[] = availableApps.map((a) => ({
    label: a.name,
    value: a.id,
  }));

  const handleSubmit = async () => {
    if (!selectedTeam) {
      throw new Error('Target team is required');
    }
    if (!selectedApp) {
      throw new Error('Application is required');
    }
    if (!selectedLevel) {
      throw new Error('Access level is required');
    }
    await onSubmit(selectedTeam.value!, selectedApp.value!, selectedLevel.value as AccessLevel);
  };

  return (
    <FormModal
      visible={visible}
      header="Grant Shared Access"
      submitLabel="Grant Access"
      onSubmit={handleSubmit}
      onDismiss={onDismiss}
      onReset={() => {
        setSelectedTeam(null);
        setSelectedApp(null);
        setSelectedLevel(null);
      }}
      errorFallback="Failed to grant access"
      testIdPrefix="grant-access"
    >
      {(error) => (
        <>
          {error && (
            <Box color="text-status-error">{error}</Box>
          )}
          <FormField label="Target team">
            <Select
              selectedOption={selectedTeam}
              onChange={({ detail }) => setSelectedTeam(detail.selectedOption)}
              options={teamOptions}
              placeholder="Select a team to share with"
              data-testid="grant-access-team-select"
            />
          </FormField>
          <FormField label="Application">
            <Select
              selectedOption={selectedApp}
              onChange={({ detail }) => setSelectedApp(detail.selectedOption)}
              options={appOptions}
              placeholder="Select an application"
              data-testid="grant-access-app-select"
            />
          </FormField>
          <FormField label="Access level">
            <Select
              selectedOption={selectedLevel}
              onChange={({ detail }) => setSelectedLevel(detail.selectedOption)}
              options={ACCESS_LEVEL_OPTIONS}
              placeholder="Select access level"
              data-testid="grant-access-level-select"
            />
          </FormField>
        </>
      )}
    </FormModal>
  );
};

export default GrantAccessModal;
