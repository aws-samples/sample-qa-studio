/**
 * FormModal — the shell of the admin form modals: header, Cancel / submit
 * footer, submitting state and the error message.
 *
 * - `onSubmit` validates and saves. Throw to keep the modal open: the error's
 *   message is shown, or `errorFallback` when it has none. Validation failures
 *   are thrown the same way (`throw new Error('Team name is required')`).
 * - On success and on Cancel/close, `onReset` clears the caller's fields,
 *   the error is cleared and `onDismiss` closes the modal.
 * - `children` receives the current error so the caller decides where it is
 *   shown (a field's `errorText` or a line above the fields).
 * - A second submit while one is in flight is ignored.
 */
import { useRef, useState, type ReactNode } from 'react';
import Modal from '@cloudscape-design/components/modal';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';

export interface FormModalProps {
  visible: boolean;
  header: string;
  submitLabel: string;
  onSubmit: () => Promise<void>;
  onDismiss: () => void;
  /** Clear the caller's field state. */
  onReset: () => void;
  errorFallback: string;
  /** Prefix of the footer buttons' test ids: `{prefix}-cancel`, `{prefix}-submit`. */
  testIdPrefix: string;
  children: (error: string | null) => ReactNode;
}

export default function FormModal({
  visible,
  header,
  submitLabel,
  onSubmit,
  onDismiss,
  onReset,
  errorFallback,
  testIdPrefix,
  children,
}: FormModalProps) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const close = () => {
    onReset();
    setError(null);
    onDismiss();
  };

  const handleSubmit = async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit();
      close();
    } catch (err) {
      setError((err as { message?: string } | null)?.message || errorFallback);
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  };

  return (
    <Modal
      visible={visible}
      onDismiss={close}
      closeAriaLabel="Close"
      header={header}
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={close} data-testid={`${testIdPrefix}-cancel`}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleSubmit}
              loading={submitting}
              data-testid={`${testIdPrefix}-submit`}
            >
              {submitLabel}
            </Button>
          </SpaceBetween>
        </Box>
      }
    >
      <SpaceBetween direction="vertical" size="m">
        {children(error)}
      </SpaceBetween>
    </Modal>
  );
}
