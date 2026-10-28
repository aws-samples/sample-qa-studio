import React, { useState } from 'react';
import Modal from '@cloudscape-design/components/modal';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';
import FormField from '@cloudscape-design/components/form-field';
import Input from '@cloudscape-design/components/input';
import Textarea from '@cloudscape-design/components/textarea';

interface CreateTeamModalProps {
  visible: boolean;
  onDismiss: () => void;
  onSubmit: (name: string, description: string) => Promise<void>;
}

const CreateTeamModal: React.FC<CreateTeamModalProps> = ({ visible, onDismiss, onSubmit }) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError('Team name is required');
      return;
    }
    try {
      setSubmitting(true);
      setError(null);
      await onSubmit(name.trim(), description.trim());
      setName('');
      setDescription('');
      onDismiss();
    } catch (err: any) {
      setError(err.message || 'Failed to create team');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDismiss = () => {
    setName('');
    setDescription('');
    setError(null);
    onDismiss();
  };

  return (
    <Modal
      visible={visible}
      onDismiss={handleDismiss}
      closeAriaLabel="Close"
      header="Create Team"
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={handleDismiss} data-testid="create-team-cancel">
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleSubmit}
              loading={submitting}
              data-testid="create-team-submit"
            >
              Create
            </Button>
          </SpaceBetween>
        </Box>
      }
    >
      <SpaceBetween direction="vertical" size="m">
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
      </SpaceBetween>
    </Modal>
  );
};

export default CreateTeamModal;
