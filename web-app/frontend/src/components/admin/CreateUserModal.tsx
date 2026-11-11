import React, { useState } from 'react';
import FormField from '@cloudscape-design/components/form-field';
import Input from '@cloudscape-design/components/input';
import Select, { SelectProps } from '@cloudscape-design/components/select';
import { Role, Team } from '../../types/permissions';
import FormModal from '../common/FormModal';

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

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const CreateUserModal: React.FC<CreateUserModalProps> = ({
  visible,
  onDismiss,
  onSubmit,
  availableTeams,
}) => {
  const [email, setEmail] = useState('');
  const [selectedTeam, setSelectedTeam] = useState<SelectProps.Option | null>(null);
  const [selectedRole, setSelectedRole] = useState<SelectProps.Option | null>(null);

  const teamOptions: SelectProps.Option[] = availableTeams.map((t) => ({
    label: t.name,
    value: t.id,
  }));

  const handleSubmit = async () => {
    if (!email.trim()) {
      throw new Error('Email is required');
    }
    if (!EMAIL_PATTERN.test(email.trim())) {
      throw new Error('Invalid email format');
    }
    // Admins are studio-wide: never send a team for them.
    const isAdminRole = selectedRole?.value === 'admin';
    await onSubmit(
      email.trim(),
      isAdminRole ? undefined : (selectedTeam?.value || undefined),
      (selectedRole?.value as Role) || undefined
    );
  };

  return (
    <FormModal
      visible={visible}
      header="Create User"
      submitLabel="Create User"
      onSubmit={handleSubmit}
      onDismiss={onDismiss}
      onReset={() => {
        setEmail('');
        setSelectedTeam(null);
        setSelectedRole(null);
      }}
      errorFallback="Failed to create user"
      testIdPrefix="create-user"
    >
      {(error) => (
        <>
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
        </>
      )}
    </FormModal>
  );
};

export default CreateUserModal;
