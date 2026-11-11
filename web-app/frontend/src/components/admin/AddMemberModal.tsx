import React, { useState } from 'react';
import FormField from '@cloudscape-design/components/form-field';
import Input from '@cloudscape-design/components/input';
import Select, { SelectProps } from '@cloudscape-design/components/select';
import { Role } from '../../types/permissions';
import FormModal from '../common/FormModal';

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

  const roleOptions: SelectProps.Option[] = allowedRoles.map((r) => ({
    label: ROLE_LABELS[r],
    value: r,
  }));

  const handleSubmit = async () => {
    if (!userId.trim()) {
      throw new Error('User email or ID is required');
    }
    if (!selectedRole) {
      throw new Error('Role is required');
    }
    await onSubmit(userId.trim(), selectedRole.value as Role);
  };

  return (
    <FormModal
      visible={visible}
      header="Add Team Member"
      submitLabel="Add Member"
      onSubmit={handleSubmit}
      onDismiss={onDismiss}
      onReset={() => {
        setUserId('');
        setSelectedRole(null);
      }}
      errorFallback="Failed to add member"
      testIdPrefix="add-member"
    >
      {(error) => (
        <>
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
        </>
      )}
    </FormModal>
  );
};

export default AddMemberModal;
