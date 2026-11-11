import { describe, it, expect, vi, afterEach } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

import FormModal, { type FormModalProps } from '../FormModal';

afterEach(() => {
  cleanup();
});

function renderModal(overrides: Partial<FormModalProps> = {}) {
  const props: FormModalProps = {
    visible: true,
    header: 'Create Thing',
    submitLabel: 'Create',
    onSubmit: vi.fn().mockResolvedValue(undefined),
    onDismiss: vi.fn(),
    onReset: vi.fn(),
    errorFallback: 'Failed to create thing',
    testIdPrefix: 'create-thing',
    children: (error) => <p data-testid="error-slot">{error ?? 'no error'}</p>,
    ...overrides,
  };
  render(<FormModal {...props} />);
  return props;
}

const submit = () => screen.getByTestId('create-thing-submit');
const cancel = () => screen.getByTestId('create-thing-cancel');

describe('FormModal', () => {
  it('renders the header, the submit label and the children', () => {
    renderModal();
    expect(screen.getByText('Create Thing')).toBeInTheDocument();
    expect(submit()).toHaveTextContent('Create');
    expect(cancel()).toHaveTextContent('Cancel');
    expect(screen.getByTestId('error-slot')).toHaveTextContent('no error');
  });

  it('closes and resets after a successful submit', async () => {
    const props = renderModal();
    fireEvent.click(submit());
    await waitFor(() => expect(props.onDismiss).toHaveBeenCalledTimes(1));
    expect(props.onSubmit).toHaveBeenCalledTimes(1);
    expect(props.onReset).toHaveBeenCalledTimes(1);
  });

  it('shows the error message and stays open when submit fails', async () => {
    const props = renderModal({ onSubmit: vi.fn().mockRejectedValue(new Error('Name is required')) });
    fireEvent.click(submit());
    await waitFor(() => expect(screen.getByTestId('error-slot')).toHaveTextContent('Name is required'));
    expect(props.onDismiss).not.toHaveBeenCalled();
    expect(props.onReset).not.toHaveBeenCalled();
  });

  it('falls back to errorFallback for an error without a message', async () => {
    renderModal({ onSubmit: vi.fn().mockRejectedValue({}) });
    fireEvent.click(submit());
    await waitFor(() => expect(screen.getByTestId('error-slot')).toHaveTextContent('Failed to create thing'));
  });

  it('clears the error when submitting again', async () => {
    const onSubmit = vi.fn().mockRejectedValueOnce(new Error('first')).mockResolvedValueOnce(undefined);
    const props = renderModal({ onSubmit });
    fireEvent.click(submit());
    await waitFor(() => expect(screen.getByTestId('error-slot')).toHaveTextContent('first'));
    fireEvent.click(submit());
    await waitFor(() => expect(props.onDismiss).toHaveBeenCalled());
    expect(screen.getByTestId('error-slot')).toHaveTextContent('no error');
  });

  it('Cancel resets the fields and the error, then dismisses', async () => {
    const props = renderModal({ onSubmit: vi.fn().mockRejectedValue(new Error('bad')) });
    fireEvent.click(submit());
    await waitFor(() => expect(screen.getByTestId('error-slot')).toHaveTextContent('bad'));

    fireEvent.click(cancel());
    expect(props.onReset).toHaveBeenCalledTimes(1);
    expect(props.onDismiss).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('error-slot')).toHaveTextContent('no error');
  });

  it('ignores a second submit while the first is in flight', async () => {
    let resolve!: () => void;
    const onSubmit = vi.fn(() => new Promise<void>((res) => { resolve = res; }));
    const props = renderModal({ onSubmit });

    fireEvent.click(submit());
    fireEvent.click(submit());
    expect(onSubmit).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolve();
    });
    expect(props.onDismiss).toHaveBeenCalledTimes(1);
  });
});
