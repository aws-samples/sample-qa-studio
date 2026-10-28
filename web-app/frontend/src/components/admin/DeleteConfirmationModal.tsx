import React, { useState } from 'react';
import Modal from '@cloudscape-design/components/modal';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';
import Alert from '@cloudscape-design/components/alert';
import Input from '@cloudscape-design/components/input';
import FormField from '@cloudscape-design/components/form-field';

interface DeleteConfirmationModalProps {
  visible: boolean;
  onDismiss: () => void;
  onConfirm: () => Promise<void>;
  entityType: string;
  entityName: string;
  /** If > 5, require type-to-confirm */
  memberCount?: number;
}

const BULK_THRESHOLD = 5;

const DeleteConfirmationModal: React.FC<DeleteConfirmationModalProps> = ({
  visible,
  onDismiss,
  onConfirm,
  entityType,
  entityName,
  memberCount = 0,
}) => {
  const [confirmText, setConfirmText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const requiresTypeConfirm = memberCount > BULK_THRESHOLD;
  const canConfirm = requiresTypeConfirm ? confirmText === entityName : true;

  const handleConfirm = async () => {
    try {
      setSubmitting(true);
      await onConfirm();
      setConfirmText('');
      onDismiss();
    } catch {
      // Error handling left to parent
    } finally {
      setSubmitting(false);
    }
  };

  const handleDismiss = () => {
    setConfirmText('');
    onDismiss();
  };

  return (
    <Modal
      visible={visible}
      onDismiss={handleDismiss}
      closeAriaLabel="Close"
      header={`Delete ${entityType}`}
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={handleDismiss} data-testid="delete-cancel">
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleConfirm}
              loading={submitting}
              disabled={!canConfirm}
              data-testid="delete-confirm"
            >
              Delete
            </Button>
          </SpaceBetween>
        </Box>
      }
    >
      <SpaceBetween direction="vertical" size="m">
        <Alert type="warning">
          This action cannot be undone. Deleting{' '}
          <Box variant="span" fontWeight="bold">{entityName}</Box>{' '}
          will permanently remove it and all associated data.
        </Alert>

        {requiresTypeConfirm && (
          <FormField
            label={`Type "${entityName}" to confirm`}
            description={`This ${entityType.toLowerCase()} has ${memberCount} members. Type the name to confirm deletion.`}
          >
            <Input
              value={confirmText}
              onChange={({ detail }) => setConfirmText(detail.value)}
              placeholder={entityName}
              data-testid="delete-confirm-input"
            />
          </FormField>
        )}
      </SpaceBetween>
    </Modal>
  );
};

export default DeleteConfirmationModal;
