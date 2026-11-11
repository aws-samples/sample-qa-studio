import React, { useState } from 'react';
import FormField from '@cloudscape-design/components/form-field';
import Input from '@cloudscape-design/components/input';
import Textarea from '@cloudscape-design/components/textarea';
import FormModal from '../common/FormModal';

interface CreateTeamModalProps {
  visible: boolean;
  onDismiss: () => void;
  onSubmit: (name: string, description: string) => Promise<void>;
}

const CreateTeamModal: React.FC<CreateTeamModalProps> = ({ visible, onDismiss, onSubmit }) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  const handleSubmit = async () => {
    if (!name.trim()) {
      throw new Error('Team name is required');
    }
    await onSubmit(name.trim(), description.trim());
  };

  return (
    <FormModal
      visible={visible}
      header="Create Team"
      submitLabel="Create"
      onSubmit={handleSubmit}
      onDismiss={onDismiss}
      onReset={() => {
        setName('');
        setDescription('');
      }}
      errorFallback="Failed to create team"
      testIdPrefix="create-team"
    >
      {(error) => (
        <>
          <FormField label="Team name" errorText={error}>
            <Input
              value={name}
              onChange={({ detail }) => setName(detail.value)}
              placeholder="Enter team name"
              data-testid="create-team-name-input"
            />
          </FormField>
          <FormField label="Description" description="Optional">
            <Textarea
              value={description}
              onChange={({ detail }) => setDescription(detail.value)}
              placeholder="Describe the team's purpose"
              data-testid="create-team-description-input"
            />
          </FormField>
        </>
      )}
    </FormModal>
  );
};

export default CreateTeamModal;
