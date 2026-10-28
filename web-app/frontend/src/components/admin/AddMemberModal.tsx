import React, { useState } from 'react';
import Modal from '@cloudscape-design/components/modal';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';
import FormField from '@cloudscape-design/components/form-field';
import Input from '@cloudscape-design/components/input';
import Select, { SelectProps } from '@cloudscape-design/components/select';
import { Role } from '../../types/permissions';

interface AddMemberModalProps {
  visible: boolean;
  onDismiss: () => void;
  onSubmit: (userId: string, role: Role) => Promise<void>;
  /** Roles that the current actor can assign */
  allowedRoles: Role[];
}

const ROLE_LABELS: Record<Role, string> = {
  admin: 'Admin',
  team_lead: 'Team Lead',
  editor: 'Editor',
  executor: 'Executor',
  viewer: 'Viewer',
};

const AddMemberModal: React.FC<AddMemberModalProps> = ({
  visible,
  onDismiss,
  onSubmit,
  allowedRoles,
}) => {
  const [userId, setUserId] = useState('');
  const [selectedRole, setSelectedRole] = useState<SelectProps.Option | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const roleOptions: SelectProps.Option[] = allowedRoles.map((r) => ({
    label: ROLE_LABELS[r],
    value: r,
  }));

  const handleSubmit = async () => {
    if (!userId.trim()) {
      setError('User email or ID is required');
      return;
    }
    if (!selectedRole) {
      setError('Role is required');
      return;
    }
    try {
      setSubmitting(true);
      setError(null);
      await onSubmit(userId.trim(), selectedRole.value as Role);
      setUserId('');
      setSelectedRole(null);
      onDismiss();
    } catch (err: any) {
      setError(err.message || 'Failed to add member');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDismiss = () => {
    setUserId('');
    setSelectedRole(null);
    setError(null);
    onDismiss();
  };

  return (
    <Modal
      visible={visible}
      onDismiss={handleDismiss}
      closeAriaLabel="Close"
      header="Add Team Member"
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={handleDismiss} data-testid="add-member-cancel">
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleSubmit}
              loading={submitting}
              data-testid="add-member-submit"
            >
              Add Member
            </Button>
          </SpaceBetween>
        </Box>
      }
    >
      <SpaceBetween direction="vertical" size="m">
        <FormField label="User email or ID" errorText={error}>
          <Input
            value={userId}
            onChange={({ detail }) => setUserId(detail.value)}
            placeholder="user@example.com or cognito-sub"
            data-testid="add-member-user-input"
          />
        </FormField>
        <FormField label="Role">
          <Select
            selectedOption={selectedRole}
            onChange={({ detail }) => setSelectedRole(detail.selectedOption)}
            options={roleOptions}
            placeholder="Select role"
            data-testid="add-member-role-select"
          />
        </FormField>
      </SpaceBetween>
    </Modal>
  );
};

export default AddMemberModal;
