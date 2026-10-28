import React, { useState } from 'react';
import Modal from '@cloudscape-design/components/modal';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';
import FormField from '@cloudscape-design/components/form-field';
import Input from '@cloudscape-design/components/input';
import Select, { SelectProps } from '@cloudscape-design/components/select';
import { Role, Team } from '../../types/permissions';

interface CreateUserModalProps {
  visible: boolean;
  onDismiss: () => void;
  onSubmit: (email: string, teamId?: string, role?: Role) => Promise<void>;
  availableTeams: Team[];
}

const ROLE_OPTIONS: SelectProps.Option[] = [
  { label: 'Admin', value: 'admin' },
  { label: 'Team Lead', value: 'team_lead' },
  { label: 'Editor', value: 'editor' },
  { label: 'Executor', value: 'executor' },
  { label: 'Viewer', value: 'viewer' },
];

const CreateUserModal: React.FC<CreateUserModalProps> = ({
  visible,
  onDismiss,
  onSubmit,
  availableTeams,
}) => {
  const [email, setEmail] = useState('');
  const [selectedTeam, setSelectedTeam] = useState<SelectProps.Option | null>(null);
  const [selectedRole, setSelectedRole] = useState<SelectProps.Option | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const teamOptions: SelectProps.Option[] = availableTeams.map((t) => ({
    label: t.name,
    value: t.id,
  }));

  const handleSubmit = async () => {
    if (!email.trim()) {
      setError('Email is required');
      return;
    }
    // Basic email validation
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError('Invalid email format');
      return;
    }
    try {
      setSubmitting(true);
      setError(null);
      const isAdminRole = selectedRole?.value === 'admin';
      await onSubmit(
        email.trim(),
        isAdminRole ? undefined : (selectedTeam?.value || undefined),
        (selectedRole?.value as Role) || undefined
      );
      setEmail('');
      setSelectedTeam(null);
      setSelectedRole(null);
      onDismiss();
    } catch (err: any) {
      setError(err.message || 'Failed to create user');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDismiss = () => {
    setEmail('');
    setSelectedTeam(null);
    setSelectedRole(null);
    setError(null);
    onDismiss();
  };

  return (
    <Modal
      visible={visible}
      onDismiss={handleDismiss}
      closeAriaLabel="Close"
      header="Create User"
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={handleDismiss} data-testid="create-user-cancel">
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleSubmit}
              loading={submitting}
              data-testid="create-user-submit"
            >
              Create User
            </Button>
          </SpaceBetween>
        </Box>
      }
    >
      <SpaceBetween direction="vertical" size="m">
        <FormField label="Email" errorText={error}>
          <Input
            value={email}
            onChange={({ detail }) => setEmail(detail.value)}
            placeholder="user@example.com"
            type="email"
            data-testid="create-user-email-input"
          />
        </FormField>
        <FormField label="Role" description="Admins have studio-wide access and are not tied to a team">
          <Select
            selectedOption={selectedRole}
            onChange={({ detail }) => setSelectedRole(detail.selectedOption)}
            options={ROLE_OPTIONS}
            placeholder="Select role (optional)"
            data-testid="create-user-role-select"
          />
        </FormField>
        {selectedRole?.value !== 'admin' && (
          <FormField label="Team" description="Optional - assign to a team">
            <Select
              selectedOption={selectedTeam}
              onChange={({ detail }) => setSelectedTeam(detail.selectedOption)}
              options={teamOptions}
              placeholder="Select team (optional)"
              data-testid="create-user-team-select"
            />
          </FormField>
        )}
      </SpaceBetween>
    </Modal>
  );
};

export default CreateUserModal;
