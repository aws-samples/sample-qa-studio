import React, { useState } from 'react';
import Modal from '@cloudscape-design/components/modal';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';
import FormField from '@cloudscape-design/components/form-field';
import Select, { SelectProps } from '@cloudscape-design/components/select';
import { AccessLevel, Team } from '../../types/permissions';

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
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      setError('Target team is required');
      return;
    }
    if (!selectedApp) {
      setError('Application is required');
      return;
    }
    if (!selectedLevel) {
      setError('Access level is required');
      return;
    }
    try {
      setSubmitting(true);
      setError(null);
      await onSubmit(
        selectedTeam.value!,
        selectedApp.value!,
        selectedLevel.value as AccessLevel
      );
      setSelectedTeam(null);
      setSelectedApp(null);
      setSelectedLevel(null);
      onDismiss();
    } catch (err: any) {
      setError(err.message || 'Failed to grant access');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDismiss = () => {
    setSelectedTeam(null);
    setSelectedApp(null);
    setSelectedLevel(null);
    setError(null);
    onDismiss();
  };

  return (
    <Modal
      visible={visible}
      onDismiss={handleDismiss}
      closeAriaLabel="Close"
      header="Grant Shared Access"
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={handleDismiss} data-testid="grant-access-cancel">
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleSubmit}
              loading={submitting}
              data-testid="grant-access-submit"
            >
              Grant Access
            </Button>
          </SpaceBetween>
        </Box>
      }
    >
      <SpaceBetween direction="vertical" size="m">
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
      </SpaceBetween>
    </Modal>
  );
};

export default GrantAccessModal;
