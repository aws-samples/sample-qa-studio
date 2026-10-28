import React, { useState, useEffect } from 'react';
import Modal from '@cloudscape-design/components/modal';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';
import FormField from '@cloudscape-design/components/form-field';
import Select, { SelectProps } from '@cloudscape-design/components/select';
import Alert from '@cloudscape-design/components/alert';
import { UserWithTeams, Team } from '../../types/permissions';

const ROLE_OPTIONS: SelectProps.Option[] = [
  { label: 'Admin', value: 'admin' },
  { label: 'Team Lead', value: 'team_lead' },
  { label: 'Editor', value: 'editor' },
  { label: 'Executor', value: 'executor' },
  { label: 'Viewer', value: 'viewer' },
];

interface EditUserModalProps {
  visible: boolean;
  onDismiss: () => void;
  onSubmit: (userId: string, updates: { teamId?: string; role?: string }) => Promise<void>;
  user: UserWithTeams | null;
  availableTeams: Team[];
}

export default function EditUserModal({ visible, onDismiss, onSubmit, user, availableTeams }: EditUserModalProps) {
  const [selectedTeam, setSelectedTeam] = useState<SelectProps.Option | null>(null);
  const [selectedRole, setSelectedRole] = useState<SelectProps.Option | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const teamOptions: SelectProps.Option[] = availableTeams.map((t) => ({
    label: t.name,
    value: t.id,
  }));

  useEffect(() => {
    if (user && visible) {
      const currentTeam = user.teams?.[0];
      if (currentTeam) {
        setSelectedTeam({ label: currentTeam.name, value: currentTeam.teamId });
        const roleOpt = ROLE_OPTIONS.find((r) => r.value === currentTeam.role);
        setSelectedRole(roleOpt || null);
      } else {
        setSelectedTeam(null);
        setSelectedRole(null);
      }
      setError('');
    }
  }, [user, visible]);

  async function handleSubmit() {
    if (!user) return;
    if (!selectedRole?.value) {
      setError('Please select a role');
      return;
    }

    const isAdminRole = selectedRole.value === 'admin';
    if (!isAdminRole && !selectedTeam?.value) {
      setError('Please select a team');
      return;
    }

    setSaving(true);
    setError('');

    try {
      await onSubmit(user.userId, {
        teamId: isAdminRole ? undefined : selectedTeam?.value,
        role: selectedRole.value,
      });
      onDismiss();
    } catch (e: any) {
      setError(e.message || 'Failed to update user');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      visible={visible}
      onDismiss={onDismiss}
      header={`Edit User: ${user?.email || ''}`}
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={onDismiss}>Cancel</Button>
            <Button variant="primary" loading={saving} onClick={handleSubmit}>Save</Button>
          </SpaceBetween>
        </Box>
      }
    >
      <SpaceBetween size="m">
        {error && <Alert type="error">{error}</Alert>}

        <FormField label="Role" description="Admins have studio-wide access and are not tied to a team">
          <Select
            selectedOption={selectedRole}
            onChange={({ detail }) => setSelectedRole(detail.selectedOption)}
            options={ROLE_OPTIONS}
            placeholder="Select a role"
          />
        </FormField>

        {selectedRole?.value !== 'admin' && (
          <FormField label="Team" description="Assign or change the user's team">
            <Select
              selectedOption={selectedTeam}
              onChange={({ detail }) => setSelectedTeam(detail.selectedOption)}
              options={teamOptions}
              placeholder="Select a team"
            />
          </FormField>
        )}
      </SpaceBetween>
    </Modal>
  );
}
