/**
 * HomeScreen "Delete Selected (n)" — the batch delete on the Use Cases page.
 *
 * Uses the real `DeleteConfirmModal`. Cloudscape renders a hidden Modal into the
 * DOM, so the dialog is reached through `createWrapper(document.body).findModal()`
 * and its footer, never by a global "Delete" button query.
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import createWrapper from '@cloudscape-design/components/test-utils/dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import HomeScreen from '../HomeScreen';

vi.mock('../../utils/api', () => ({
  api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

import { api } from '../../utils/api';

const apiGet = api.get as ReturnType<typeof vi.fn>;
const apiDelete = api.delete as ReturnType<typeof vi.fn>;

// Rows render sorted by name: Alpha (row 1), Middle (row 2), Zebra (row 3).
const USECASES = [
  { id: 'uc-z', name: 'Zebra Test', description: 'zebra', active: true },
  { id: 'uc-a', name: 'Alpha Test', description: 'alpha', active: true },
  { id: 'uc-m', name: 'Middle Test', description: 'middle', active: false },
];

const wrapper = () => createWrapper(document.body);
const dropdown = () => wrapper().findButtonDropdown()!;
const modal = () => wrapper().findModal()!;

async function renderLoaded() {
  render(
    <MemoryRouter>
      <HomeScreen />
    </MemoryRouter>,
  );
  await screen.findByText('Zebra Test');
}

function selectRow(index: number) {
  act(() => wrapper().findTable()!.findRowSelectionArea(index)!.click());
}

function openDropdown() {
  act(() => dropdown().openDropdown());
}

function deleteItem() {
  openDropdown();
  return dropdown().findItemById('delete-selected')!;
}

function clickDeleteSelected() {
  // Open outside the click's act() so the dropdown has rendered its items.
  const item = deleteItem();
  act(() => item.click());
}

function footerButton(name: 'Cancel' | 'Delete') {
  const buttons = Array.from(modal().findFooter()!.getElement().querySelectorAll('button'));
  return buttons.find((b) => b.textContent?.trim() === name)!;
}

function confirmDeletion() {
  fireEvent.change(screen.getByLabelText('Confirmation text'), { target: { value: 'permanently delete' } });
  fireEvent.click(footerButton('Delete'));
}

describe('HomeScreen "Delete Selected"', () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiDelete.mockReset();
    apiGet.mockResolvedValue({ usecases: USECASES });
    apiDelete.mockResolvedValue(undefined);
  });

  it('is disabled when nothing is selected', async () => {
    await renderLoaded();
    const item = deleteItem();
    expect(item.getElement().textContent).toContain('Delete Selected (0)');
    expect(item.find('[role="menuitem"]')!.getElement()).toHaveAttribute('aria-disabled', 'true');
  });

  it('opens the confirmation modal with the selected count', async () => {
    await renderLoaded();
    selectRow(1);
    selectRow(3);
    const item = deleteItem();
    expect(item.getElement().textContent).toContain('Delete Selected (2)');
    expect(item.find('[role="menuitem"]')!.getElement()).not.toHaveAttribute('aria-disabled');
    act(() => item.click());

    expect(modal().isVisible()).toBe(true);
    expect(modal().findHeader().getElement().textContent).toBe('Delete Use Cases');
    expect(
      screen.getByText(
        'You are about to permanently delete 2 use cases. This will remove all associated data including steps, executions, and configurations.',
      ),
    ).toBeInTheDocument();
    expect(footerButton('Delete')).toBeDisabled();
    expect(apiDelete).not.toHaveBeenCalled();
  });

  it('deletes each selected use case, shows success, clears the selection and reloads', async () => {
    await renderLoaded();
    selectRow(1);
    selectRow(3);
    clickDeleteSelected();
    apiGet.mockResolvedValue({ usecases: [USECASES[2]] });

    confirmDeletion();

    expect(await screen.findByText('Successfully deleted 2 use case(s)')).toBeInTheDocument();
    expect(apiDelete).toHaveBeenCalledTimes(2);
    expect(apiDelete).toHaveBeenCalledWith('usecase/uc-a');
    expect(apiDelete).toHaveBeenCalledWith('usecase/uc-z');
    expect(screen.queryByText(/Failed to delete/)).not.toBeInTheDocument();

    await waitFor(() => expect(screen.queryByText('Zebra Test')).not.toBeInTheDocument());
    expect(screen.queryByText('Alpha Test')).not.toBeInTheDocument();
    expect(screen.getByText('Middle Test')).toBeInTheDocument();
    expect(apiGet).toHaveBeenCalledTimes(2);
    expect(apiGet).toHaveBeenLastCalledWith('usecases');
    expect(deleteItem().getElement().textContent).toContain('Delete Selected (0)');
  });

  it('shows the in-progress flash while the batch runs', async () => {
    let finish: () => void = () => undefined;
    apiDelete.mockReturnValue(new Promise<void>((resolve) => { finish = resolve; }));
    await renderLoaded();
    selectRow(2);
    clickDeleteSelected();

    confirmDeletion();

    expect(await screen.findByText('Deleting 1 use case(s)...')).toBeInTheDocument();
    expect(modal().isVisible()).toBe(false);
    await act(async () => { finish(); });
    expect(await screen.findByText('Successfully deleted 1 use case(s)')).toBeInTheDocument();
    expect(screen.queryByText('Deleting 1 use case(s)...')).not.toBeInTheDocument();
  });

  it('names the failed use case on a partial failure', async () => {
    apiDelete.mockImplementation(async (endpoint: string) => {
      if (endpoint === 'usecase/uc-z') throw new Error('Forbidden');
    });
    await renderLoaded();
    selectRow(1);
    selectRow(3);
    clickDeleteSelected();

    confirmDeletion();

    expect(await screen.findByText('Failed to delete 1 use case(s): Zebra Test')).toBeInTheDocument();
    expect(screen.getByText('Successfully deleted 1 use case(s)')).toBeInTheDocument();
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(2));
    expect(deleteItem().getElement().textContent).toContain('Delete Selected (0)');
  });

  it('deletes nothing and keeps the selection when cancelled', async () => {
    await renderLoaded();
    selectRow(1);
    selectRow(2);
    clickDeleteSelected();
    expect(modal().isVisible()).toBe(true);

    fireEvent.click(footerButton('Cancel'));

    await waitFor(() => expect(modal().isVisible()).toBe(false));
    expect(apiDelete).not.toHaveBeenCalled();
    expect(apiGet).toHaveBeenCalledTimes(1);
    expect(deleteItem().getElement().textContent).toContain('Delete Selected (2)');
  });
});
