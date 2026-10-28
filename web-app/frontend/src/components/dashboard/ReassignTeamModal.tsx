import React, { useState, useEffect } from 'react';
import Modal from '@cloudscape-design/components/modal';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';
import FormField from '@cloudscape-design/components/form-field';
import Select, { SelectProps } from '@cloudscape-design/components/select';
import Alert from '@cloudscape-design/components/alert';
import { api } from '../../utils/api';

interface ReassignTeamModalProps {
  visible: boolean;
  onDismiss: () => void;
  onSuccess: () => void;
  applicationId: string;
  applicationName: string;
  currentTeamId?: string;
}

export function ReassignTeamModal({ visible, onDismiss, onSuccess, applicationId, applicationName, currentTeamId }: ReassignTeamModalProps) {
  const [selectedTeam, setSelectedTeam] = useState<SelectProps.Option | null>(null);
  const [teamOptions, setTeamOptions] = useState<SelectProps.Option[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (visible) {
      api.get('teams').then((data: any) => {
        const teams = data.teams || data || [];
        setTeamOptions(
          teams
            .filter((t: any) => t.id !== currentTeamId)
            .map((t: any) => ({ label: t.name, value: t.id }))
        );
      }).catch(() => setTeamOptions([]));
      setSelectedTeam(null);
      setError('');
    }
  }, [visible, currentTeamId]);

  async function handleSubmit() {
    if (!selectedTeam?.value) {
      setError('Please select a team');
      return;
    }

    setSaving(true);
    setError('');

    try {
      await api.post(`applications/${applicationId}/reassign`, { targetTeamId: selectedTeam.value });
      onSuccess();
      onDismiss();
    } catch (e: any) {
      setError(e.message || 'Failed to reassign application');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      visible={visible}
      onDismiss={onDismiss}
      header={`Reassign "${applicationName}" to team`}
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={onDismiss}>Cancel</Button>
            <Button variant="primary" loading={saving} disabled={!selectedTeam} onClick={handleSubmit}>
              Reassign
            </Button>
          </SpaceBetween>
        </Box>
      }
    >
      <SpaceBetween size="m">
        {error && <Alert type="error">{error}</Alert>}
        <FormField label="Target team" description="The application will be owned by this team. Only team members will have access.">
          <Select
            selectedOption={selectedTeam}
            onChange={({ detail }) => setSelectedTeam(detail.selectedOption)}
            options={teamOptions}
            placeholder="Select a team"
            empty="No teams available"
          />
        </FormField>
      </SpaceBetween>
    </Modal>
  );
}
