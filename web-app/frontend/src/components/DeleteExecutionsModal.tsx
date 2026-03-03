import { useState } from 'react';
import Modal from "@cloudscape-design/components/modal";
import Box from "@cloudscape-design/components/box";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Input from "@cloudscape-design/components/input";
import Alert from "@cloudscape-design/components/alert";

interface DeleteExecutionsModalProps {
  visible: boolean;
  executionCount: number;
  onDismiss: () => void;
  onConfirm: () => void;
  deleting?: boolean;
}

export default function DeleteExecutionsModal({
  visible,
  executionCount,
  onDismiss,
  onConfirm,
  deleting = false
}: DeleteExecutionsModalProps) {
  const [confirmationText, setConfirmationText] = useState('');
  const requiredText = 'permanently delete';
  const isConfirmed = confirmationText.toLowerCase() === requiredText;

  const handleDismiss = () => {
    setConfirmationText('');
    onDismiss();
  };

  const handleConfirm = () => {
    if (isConfirmed) {
      setConfirmationText('');
      onConfirm();
    }
  };

  return (
    <Modal
      visible={visible}
      onDismiss={handleDismiss}
      header="Delete Executions"
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={handleDismiss} disabled={deleting}>
              Cancel
            </Button>
            <Button 
              variant="primary" 
              onClick={handleConfirm} 
              disabled={!isConfirmed || deleting}
              loading={deleting}
            >
              Delete
            </Button>
          </SpaceBetween>
        </Box>
      }
    >
      <SpaceBetween size="m">
        <Alert type="warning" header="This action cannot be undone">
          You are about to permanently delete {executionCount} execution{executionCount > 1 ? 's' : ''}. 
          This will remove all associated data including steps, logs, and results.
        </Alert>

        <Box>
          <SpaceBetween size="xs">
            <Box variant="p">
              To confirm deletion, please type <strong>{requiredText}</strong> in the field below:
            </Box>
            <Input
              value={confirmationText}
              onChange={({ detail }) => setConfirmationText(detail.value)}
              placeholder={requiredText}
              disabled={deleting}
              ariaLabel="Confirmation text"
            />
          </SpaceBetween>
        </Box>
      </SpaceBetween>
    </Modal>
  );
}
