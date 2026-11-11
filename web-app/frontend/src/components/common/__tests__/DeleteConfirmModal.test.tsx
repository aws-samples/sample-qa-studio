/**
 * DeleteConfirmModal / TypedDeleteModal — the typed "permanently delete"
 * confirmation used by batch deletes (use cases, executions) and templates.
 * The exact strings are asserted: they are what users and QA journeys see.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import DeleteConfirmModal, { TypedDeleteModal, type DeleteNoun } from '../DeleteConfirmModal';

afterEach(() => {
  cleanup();
});

const USE_CASE: DeleteNoun = { singular: 'use case', plural: 'use cases', title: 'Use Cases' };
const EXECUTION: DeleteNoun = { singular: 'execution', plural: 'executions', title: 'Executions' };
const USE_CASE_CONSEQUENCES =
  'This will remove all associated data including steps, executions, and configurations.';
const EXECUTION_CONSEQUENCES = 'This will remove all associated data including steps, logs, and results.';

function renderModal(overrides: Partial<Parameters<typeof DeleteConfirmModal>[0]> = {}) {
  const props = {
    visible: true,
    count: 2,
    noun: USE_CASE,
    consequences: USE_CASE_CONSEQUENCES,
    onConfirm: vi.fn(),
    onDismiss: vi.fn(),
    ...overrides,
  };
  render(<DeleteConfirmModal {...props} />);
  return props;
}

function deleteButton() {
  return screen.getByRole('button', { name: 'Delete' });
}

function typeConfirmation(text: string) {
  fireEvent.change(screen.getByLabelText('Confirmation text'), { target: { value: text } });
}

describe('DeleteConfirmModal — text', () => {
  it('renders the plural use-case text unchanged', () => {
    renderModal({ count: 3 });
    expect(screen.getByText('Delete Use Cases')).toBeInTheDocument();
    expect(screen.getByText('This action cannot be undone')).toBeInTheDocument();
    expect(
      screen.getByText(`You are about to permanently delete 3 use cases. ${USE_CASE_CONSEQUENCES}`),
    ).toBeInTheDocument();
  });

  it('uses the singular noun for exactly one item', () => {
    renderModal({ count: 1 });
    expect(
      screen.getByText(`You are about to permanently delete 1 use case. ${USE_CASE_CONSEQUENCES}`),
    ).toBeInTheDocument();
  });

  it('renders the execution text unchanged', () => {
    renderModal({ count: 2, noun: EXECUTION, consequences: EXECUTION_CONSEQUENCES });
    expect(screen.getByText('Delete Executions')).toBeInTheDocument();
    expect(
      screen.getByText(
        'You are about to permanently delete 2 executions. This will remove all associated data including steps, logs, and results.',
      ),
    ).toBeInTheDocument();
  });

  it('asks the user to type the confirmation phrase', () => {
    renderModal();
    expect(screen.getByText('permanently delete', { selector: 'strong' })).toBeInTheDocument();
    expect(screen.getByLabelText('Confirmation text')).toHaveAttribute('placeholder', 'permanently delete');
  });
});

describe('DeleteConfirmModal — confirm and dismiss', () => {
  it('keeps Delete disabled until the phrase is typed', () => {
    const props = renderModal();
    expect(deleteButton()).toBeDisabled();
    typeConfirmation('permanently');
    expect(deleteButton()).toBeDisabled();
    fireEvent.click(deleteButton());
    expect(props.onConfirm).not.toHaveBeenCalled();
  });

  it('confirms once the phrase is typed (case-insensitive) and clears the input', () => {
    const props = renderModal();
    typeConfirmation('Permanently Delete');
    expect(deleteButton()).not.toBeDisabled();
    fireEvent.click(deleteButton());
    expect(props.onConfirm).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('Confirmation text')).toHaveValue('');
  });

  it('dismisses via Cancel and clears the input', () => {
    const props = renderModal();
    typeConfirmation('permanently delete');
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(props.onDismiss).toHaveBeenCalledTimes(1);
    expect(props.onConfirm).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Confirmation text')).toHaveValue('');
  });
});

describe('DeleteConfirmModal — loading', () => {
  it('disables Cancel, Delete and the input while deleting', () => {
    renderModal({ loading: true });
    typeConfirmation('permanently delete');
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Delete/ })).toBeDisabled();
    expect(screen.getByLabelText('Confirmation text')).toBeDisabled();
  });
});

describe('TypedDeleteModal', () => {
  it('renders a custom warning and extra content above the input', () => {
    render(
      <TypedDeleteModal
        visible
        header="Delete Template"
        warning={<>Template <strong>Login</strong> goes away.</>}
        onConfirm={vi.fn()}
        onDismiss={vi.fn()}
      >
        <p>Used by 2 tests</p>
      </TypedDeleteModal>,
    );
    expect(screen.getByText('Delete Template')).toBeInTheDocument();
    expect(screen.getByText('Login', { selector: 'strong' })).toBeInTheDocument();
    expect(screen.getByText('Used by 2 tests')).toBeInTheDocument();
  });
});
