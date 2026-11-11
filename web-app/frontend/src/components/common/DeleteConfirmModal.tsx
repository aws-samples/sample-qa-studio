/**
 * Delete confirmation modals that require typing "permanently delete".
 *
 * - `TypedDeleteModal` is the shell (header, warning, confirmation input,
 *   Cancel/Delete footer). Use it when the warning is not a plain count, e.g.
 *   `DeleteTemplateModal`.
 * - `DeleteConfirmModal` is the batch-delete variant: "You are about to
 *   permanently delete {count} {noun}. {consequences}".
 */
import { useState, type ReactNode } from 'react';
import Modal from "@cloudscape-design/components/modal";
import Box from "@cloudscape-design/components/box";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Input from "@cloudscape-design/components/input";
import Alert from "@cloudscape-design/components/alert";

const DELETE_CONFIRMATION_TEXT = 'permanently delete';

export interface TypedDeleteModalProps {
  visible: boolean;
  header: string;
  /** Body of the "This action cannot be undone" warning. */
  warning: ReactNode;
  /** Extra content rendered between the warning and the confirmation input. */
  children?: ReactNode;
  onConfirm: () => void;
  onDismiss: () => void;
  loading?: boolean;
}

export function TypedDeleteModal({
  visible,
  header,
  warning,
  children,
  onConfirm,
  onDismiss,
  loading = false,
}: TypedDeleteModalProps) {
  const [confirmationText, setConfirmationText] = useState('');
  const isConfirmed = confirmationText.toLowerCase() === DELETE_CONFIRMATION_TEXT;

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
      header={header}
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={handleDismiss} disabled={loading}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleConfirm}
              disabled={!isConfirmed || loading}
              loading={loading}
            >
              Delete
            </Button>
          </SpaceBetween>
        </Box>
      }
    >
      <SpaceBetween size="m">
        <Alert type="warning" header="This action cannot be undone">
          {warning}
        </Alert>

        {children}

        <Box>
          <SpaceBetween size="xs">
            <Box variant="p">
              To confirm deletion, please type <strong>{DELETE_CONFIRMATION_TEXT}</strong> in the field below:
            </Box>
            <Input
              value={confirmationText}
              onChange={({ detail }) => setConfirmationText(detail.value)}
              placeholder={DELETE_CONFIRMATION_TEXT}
              disabled={loading}
              ariaLabel="Confirmation text"
            />
          </SpaceBetween>
        </Box>
      </SpaceBetween>
    </Modal>
  );
}

export interface DeleteNoun {
  /** e.g. "use case" — used when count === 1. */
  singular: string;
  /** e.g. "use cases" — used for every other count. */
  plural: string;
  /** e.g. "Use Cases" — the modal header reads "Delete {title}". */
  title: string;
}

export interface DeleteConfirmModalProps {
  visible: boolean;
  count: number;
  noun: DeleteNoun;
  /** Sentence appended to the warning, e.g. "This will remove all associated data …". */
  consequences: string;
  onConfirm: () => void;
  onDismiss: () => void;
  loading?: boolean;
}

export default function DeleteConfirmModal({
  visible,
  count,
  noun,
  consequences,
  onConfirm,
  onDismiss,
  loading = false,
}: DeleteConfirmModalProps) {
  const counted = count === 1 ? noun.singular : noun.plural;
  return (
    <TypedDeleteModal
      visible={visible}
      header={`Delete ${noun.title}`}
      warning={`You are about to permanently delete ${count} ${counted}. ${consequences}`}
      onConfirm={onConfirm}
      onDismiss={onDismiss}
      loading={loading}
    />
  );
}
