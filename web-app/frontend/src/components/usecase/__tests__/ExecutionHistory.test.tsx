/**
 * ExecutionHistory — the single-select (radio) execution table on the use case
 * page. Selection is controlled by the parent (`selectedExecutionId` /
 * `onSelectExecution`); Delete removes the one selected execution.
 *
 * Cloudscape Modal renders into a portal; the table is found through
 * `createWrapper(document.body)`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import createWrapper from '@cloudscape-design/components/test-utils/dom';

vi.mock('aws-amplify/auth', () => ({ fetchAuthSession: vi.fn() }));

const { apiGet, apiDelete } = vi.hoisted(() => ({ apiGet: vi.fn(), apiDelete: vi.fn() }));
vi.mock('../../../utils/api', async () => {
  const actual = await vi.importActual<typeof import('../../../utils/api')>('../../../utils/api');
  return {
    ...actual,
    api: { get: (...a: unknown[]) => apiGet(...a), delete: (...a: unknown[]) => apiDelete(...a) },
  };
});

import ExecutionHistory from '../ExecutionHistory';
import { executionIdOf } from '../../../utils/api';

const EXECUTIONS = [
  { pk: 'USECASE#u-1', sk: 'EXECUTION#exec-1', status: 'success', created_at: '2026-03-04T05:06:07Z', trigger_type: 'OnDemand' },
  { pk: 'USECASE#u-1', sk: 'EXECUTION#exec-2', status: 'failed', created_at: '2026-03-03T05:06:07Z' },
];

const table = () => createWrapper(document.body).findTable()!;

/** Rows as arrays of cell texts (selection column excluded). */
const rowTexts = () =>
  table().findRows().map((row) =>
    row.findAll('td, th').slice(1).map((cell) => cell.getElement().textContent?.trim()));

const radio = (index: number) => table().findRowSelectionArea(index)!.find('input')!.getElement() as HTMLInputElement;

/** The header Delete button; the (hidden) modal footer also renders a "Delete" button inside a dialog. */
const deleteButton = () =>
  screen.getAllByRole('button', { name: 'Delete' }).find((b) => !b.closest('[role="dialog"]'))!;

async function renderLoaded(selectedExecutionId: string | null = null, onSelectExecution = vi.fn()) {
  apiGet.mockResolvedValue({ executions: EXECUTIONS });
  const view = render(
    <ExecutionHistory usecaseId="u-1" selectedExecutionId={selectedExecutionId} onSelectExecution={onSelectExecution} />,
  );
  await screen.findByText('exec-1');
  return { ...view, onSelectExecution };
}

async function confirmDelete() {
  fireEvent.click(deleteButton());
  expect(await screen.findByText('Delete Executions')).toBeInTheDocument();
  expect(screen.getByText(/permanently delete 1 execution\./)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Confirmation text'), { target: { value: 'permanently delete' } });
  const confirm = screen.getAllByRole('button', { name: 'Delete' }).find((b) => b.closest('[role="dialog"]'))!;
  fireEvent.click(confirm);
}

beforeEach(() => {
  apiGet.mockReset();
  apiDelete.mockReset();
});
afterEach(() => {
  cleanup();
});

describe('executionIdOf', () => {
  it('strips the EXECUTION# prefix from the sort key', () => {
    expect(executionIdOf({ sk: 'EXECUTION#abc-123' } as never)).toBe('abc-123');
  });
});

describe('ExecutionHistory — table', () => {
  it('loads the executions and renders one radio per row with the id as plain text', async () => {
    await renderLoaded();
    expect(apiGet).toHaveBeenCalledWith('usecase/u-1/executions');
    expect(rowTexts().map((r) => r[0])).toEqual(['exec-1', 'exec-2']);
    expect(rowTexts()[0][1]).toBe('success');
    expect(rowTexts()[0][3]).toBe('OnDemand');
    expect(rowTexts()[1][3]).toBe('Manual');
    expect(radio(1).type).toBe('radio');
    expect(radio(2).type).toBe('radio');
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByRole('button', { name: 'Refresh execution history' })).toBeInTheDocument();
  });

  it('selecting a row calls onSelectExecution with the bare id', async () => {
    const { onSelectExecution } = await renderLoaded();
    fireEvent.click(radio(2));
    expect(onSelectExecution).toHaveBeenCalledWith('exec-2');
  });

  it('reflects selectedExecutionId as the selected row', async () => {
    await renderLoaded('exec-2');
    const selected = table().findSelectedRows();
    expect(selected).toHaveLength(1);
    expect(selected[0].getElement().textContent).toContain('exec-2');
    expect(radio(2).checked).toBe(true);
    expect(radio(1).checked).toBe(false);
  });

  it('selects nothing when selectedExecutionId is not in the list', async () => {
    await renderLoaded('gone');
    expect(table().findSelectedRows()).toHaveLength(0);
    expect(deleteButton()).toBeDisabled();
  });

  it('shows the empty state without executions', async () => {
    apiGet.mockResolvedValue({ executions: [] });
    render(<ExecutionHistory usecaseId="u-1" selectedExecutionId={null} onSelectExecution={vi.fn()} />);
    expect(await screen.findByText('No executions')).toBeInTheDocument();
  });

  it('Refresh reloads the list', async () => {
    await renderLoaded();
    expect(apiGet).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Refresh execution history' }));
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(2));
  });
});

describe('ExecutionHistory — delete', () => {
  it('Delete is disabled without a selection and enabled with one', async () => {
    const { rerender } = await renderLoaded();
    expect(deleteButton()).toBeDisabled();
    rerender(<ExecutionHistory usecaseId="u-1" selectedExecutionId="exec-1" onSelectExecution={vi.fn()} />);
    expect(deleteButton()).toBeEnabled();
  });

  it('deletes the selected execution, refetches and clears the selection', async () => {
    apiDelete.mockResolvedValue(null);
    const { onSelectExecution } = await renderLoaded('exec-1');

    await confirmDelete();

    await waitFor(() => expect(apiDelete).toHaveBeenCalledWith('usecase/u-1/executions/exec-1'));
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(onSelectExecution).toHaveBeenCalledWith(null));
    expect(await screen.findByText('Deleted execution exec-1')).toBeInTheDocument();
  });

  it('a failed delete shows an error Flashbar and keeps the selection', async () => {
    apiDelete.mockRejectedValue(new Error('boom'));
    const { onSelectExecution } = await renderLoaded('exec-1');

    await confirmDelete();

    expect(await screen.findByText('Failed to delete execution exec-1: boom')).toBeInTheDocument();
    expect(onSelectExecution).not.toHaveBeenCalled();
    expect(apiGet).toHaveBeenCalledTimes(1);
    expect(table().findSelectedRows()).toHaveLength(1);
    expect(deleteButton()).toBeEnabled();
  });

  it('Cancel in the modal deletes nothing', async () => {
    await renderLoaded('exec-1');
    const modal = () => createWrapper(document.body).findModal()!;
    fireEvent.click(deleteButton());
    await waitFor(() => expect(modal().isVisible()).toBe(true));
    modal().findDismissButton()!.click();
    await waitFor(() => expect(modal().isVisible()).toBe(false));
    expect(apiDelete).not.toHaveBeenCalled();
  });
});
