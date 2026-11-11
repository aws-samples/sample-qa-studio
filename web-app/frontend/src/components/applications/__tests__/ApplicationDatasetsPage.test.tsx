/**
 * ApplicationDatasetsPage — the datasets table inside the ApplicationConfigPage
 * shell: list, filter, selection-based header actions, create / edit through
 * DatasetFormModal, delete with the typed confirmation and the 409 answer, the
 * read-only view, and the paginated View modal.
 *
 * Cloudscape Modal / Select render into a portal; queries go through `screen`
 * and `createWrapper(document.body)`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import createWrapper from '@cloudscape-design/components/test-utils/dom';

const mockUsePermissions = vi.fn();
vi.mock('../../../auth', async () => {
  const access = await vi.importActual<typeof import('../../../auth/applicationAccess')>('../../../auth/applicationAccess');
  return { ...access, usePermissions: () => mockUsePermissions() };
});

const { apiGet, datasetsApi } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  datasetsApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
}));
vi.mock('../../../utils/api', () => ({
  api: { get: (...a: unknown[]) => apiGet(...a) },
  datasetsApi,
}));

import ApplicationDatasetsPage from '../ApplicationDatasetsPage';
import type { ApplicationDataset, ApplicationDatasetSummary } from '../../../utils/api';

const perms = (isAdmin: boolean, teams: Array<{ team_id: string; role: string }>) => ({
  isAdmin,
  isTeamLead: teams.some((t) => t.role === 'team_lead'),
  teams: teams.map((t) => ({ ...t, group_name: `team-${t.team_id}-${t.role}` })),
  hasScope: () => true,
  scopes: [],
  isLoading: false,
});

const app = { id: 'app-1', name: 'Shop', base_url: 'https://shop.test', description: '', team: 'A',
  owner_team_id: 'team-a', environments: [] };

const CUSTOMERS: ApplicationDatasetSummary = {
  dataset_id: 'ds-1', name: 'customers', description: 'Shop customers', column_count: 2, row_count: 2,
  updated_at: '2026-03-04T05:06:07Z',
};
const PRODUCTS: ApplicationDatasetSummary = {
  dataset_id: 'ds-2', name: 'products', description: 'Catalogue rows', column_count: 3, row_count: 7,
  updated_at: '2026-03-01T00:00:00Z',
};
const CUSTOMERS_FULL: ApplicationDataset = {
  dataset_id: 'ds-1', name: 'customers', description: 'Shop customers',
  columns: ['email', 'role'], rows: [['a@x.test', 'admin'], ['b@x.test', 'viewer']],
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-03-04T05:06:07Z', created_by: 'alice',
};

const httpError = (status: number, body: Record<string, unknown>) => ({
  type: 'validation', message: String(body.error), retryable: false, status, body,
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/applications/app-1/datasets']}>
      <Routes>
        <Route path="/applications/:id/datasets" element={<ApplicationDatasetsPage />} />
        <Route path="/usecases/:id" element={<div>usecase page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

const table = () => createWrapper(document.body).findTable()!;

/** Rows of the datasets table as arrays of cell texts (selection column excluded; Name is a row header). */
const rowTexts = () =>
  table().findRows().map((row) =>
    row.findAll('td, th').slice(1).map((cell) => cell.getElement().textContent?.trim()));

/** Select the dataset table row (1-based) through its radio input. */
function selectRow(index: number) {
  const radio = table().findRowSelectionArea(index)!.find('input')!.getElement();
  fireEvent.click(radio);
}

const button = (name: string) => screen.getByRole('button', { name });

/** Cloudscape Input renders the testid on a wrapper; the <input> is inside. */
function typeInto(testId: string, value: string) {
  const el = screen.getByTestId(testId);
  const input = el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' ? el : (el.querySelector('input, textarea') as HTMLElement);
  fireEvent.change(input, { target: { value } });
}

async function renderLoaded(datasets: ApplicationDatasetSummary[] = [CUSTOMERS, PRODUCTS]) {
  apiGet.mockResolvedValue(app);
  datasetsApi.list.mockResolvedValue({ datasets });
  renderPage();
  await screen.findByRole('heading', { name: 'Datasets' });
  if (datasets.length > 0) await screen.findByText(datasets[0].name);
  else await screen.findByText('No datasets');
}

beforeEach(() => {
  apiGet.mockReset();
  Object.values(datasetsApi).forEach((fn) => { fn.mockReset(); });
  mockUsePermissions.mockReset();
  mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'team_lead' }]));
});
afterEach(() => {
  cleanup();
});

describe('ApplicationDatasetsPage — list', () => {
  it('lists the datasets with name, description, counts and the formatted update time', async () => {
    await renderLoaded();
    expect(datasetsApi.list).toHaveBeenCalledWith('app-1');
    const rows = rowTexts();
    expect(rows).toHaveLength(2);
    expect(rows[0].slice(0, 4)).toEqual(['customers', 'Shop customers', '2', '2']);
    expect(rows[0][4]).toMatch(/^2026-03-0\d \d\d:\d\d:\d\d$/);
    expect(rows[1].slice(0, 4)).toEqual(['products', 'Catalogue rows', '3', '7']);
    expect(screen.getByText('(2)')).toBeInTheDocument();
  });

  it('filters by name', async () => {
    await renderLoaded();
    fireEvent.change(screen.getByPlaceholderText('Find datasets by name'), { target: { value: 'prod' } });
    await waitFor(() => expect(screen.queryByText('customers')).toBeNull());
    expect(screen.getByText('products')).toBeInTheDocument();
    // countText renders twice (visible + live region).
    expect(screen.getAllByText('1 match').length).toBeGreaterThan(0);
  });

  it('shows the empty state', async () => {
    await renderLoaded([]);
    expect(screen.getByText('No datasets')).toBeInTheDocument();
  });

  it('shows a load error', async () => {
    apiGet.mockResolvedValue(app);
    datasetsApi.list.mockRejectedValue(new Error('boom'));
    renderPage();
    expect(await screen.findByText('boom')).toBeInTheDocument();
  });

  it('disables the selection-based actions until a dataset is selected', async () => {
    await renderLoaded();
    for (const name of ['View', 'Edit', 'Delete']) {
      expect(button(name)).toHaveAttribute('aria-disabled', 'true');
    }
    expect(button('Create dataset')).not.toHaveAttribute('aria-disabled');
    expect(screen.getAllByText('Select a dataset first').length).toBeGreaterThan(0);

    selectRow(1);
    await waitFor(() => expect(button('Edit')).not.toHaveAttribute('aria-disabled'));
    expect(button('View')).not.toHaveAttribute('aria-disabled');
    expect(button('Delete')).not.toHaveAttribute('aria-disabled');
  });
});

describe('ApplicationDatasetsPage — create', () => {
  it('Create dataset opens the form and POSTs the body, then reloads the list', async () => {
    const user = userEvent.setup();
    await renderLoaded([CUSTOMERS]);
    const created: ApplicationDataset = {
      ...CUSTOMERS_FULL, dataset_id: 'ds-9', name: 'leads', description: '', columns: ['email'], rows: [['x@x.test']],
    };
    datasetsApi.create.mockResolvedValue({ dataset: created });
    datasetsApi.list.mockResolvedValue({ datasets: [CUSTOMERS, { ...CUSTOMERS, dataset_id: 'ds-9', name: 'leads', description: '', column_count: 1, row_count: 1 }] });

    // No modal is mounted until it is needed.
    expect(screen.queryByTestId('dataset-form-submit')).toBeNull();
    fireEvent.click(button('Create dataset'));
    expect(await screen.findByRole('dialog', { name: 'Create dataset' })).toBeInTheDocument();

    typeInto('dataset-form-name-input', 'leads');
    await user.clear(screen.getByLabelText('Column 1 name'));
    await user.type(screen.getByLabelText('Column 1 name'), 'email');
    await user.type(screen.getByLabelText('Row 1, email'), 'x@x.test');
    fireEvent.click(screen.getByTestId('dataset-form-submit'));

    await waitFor(() => expect(datasetsApi.create).toHaveBeenCalledWith('app-1', {
      name: 'leads', description: '', columns: ['email'], rows: [['x@x.test']],
    }));
    await waitFor(() => expect(datasetsApi.list).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('leads')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId('dataset-form-submit')).toBeNull());
  });
});

describe('ApplicationDatasetsPage — edit', () => {
  it('Edit loads the full dataset, pre-fills the form and PUTs the replacement', async () => {
    const user = userEvent.setup();
    await renderLoaded();
    datasetsApi.get.mockResolvedValue({ dataset: CUSTOMERS_FULL });
    const updated = { ...CUSTOMERS_FULL, rows: [...CUSTOMERS_FULL.rows, ['c@x.test', 'viewer']] };
    datasetsApi.update.mockResolvedValue({ dataset: updated });

    selectRow(1);
    await waitFor(() => expect(button('Edit')).not.toHaveAttribute('aria-disabled'));
    fireEvent.click(button('Edit'));

    await waitFor(() => expect(datasetsApi.get).toHaveBeenCalledWith('app-1', 'ds-1'));
    expect(await screen.findByText('Edit dataset')).toBeInTheDocument();
    expect(screen.getByLabelText('Row 2, role')).toHaveValue('viewer');

    await user.click(screen.getByRole('button', { name: 'Add row' }));
    await user.type(screen.getByLabelText('Row 3, email'), 'c@x.test');
    await user.type(screen.getByLabelText('Row 3, role'), 'viewer');
    fireEvent.click(screen.getByTestId('dataset-form-submit'));

    await waitFor(() => expect(datasetsApi.update).toHaveBeenCalledWith('app-1', 'ds-1', {
      name: 'customers',
      description: 'Shop customers',
      columns: ['email', 'role'],
      rows: [['a@x.test', 'admin'], ['b@x.test', 'viewer'], ['c@x.test', 'viewer']],
    }));
    await waitFor(() => expect(datasetsApi.list).toHaveBeenCalledTimes(2));
  });

  it('shows an error when the dataset cannot be loaded for editing', async () => {
    await renderLoaded();
    datasetsApi.get.mockRejectedValue(new Error('Dataset not found'));
    selectRow(1);
    await waitFor(() => expect(button('Edit')).not.toHaveAttribute('aria-disabled'));
    fireEvent.click(button('Edit'));
    expect(await screen.findByText('Dataset not found')).toBeInTheDocument();
    expect(screen.queryByText('Edit dataset')).toBeNull();
  });
});

describe('ApplicationDatasetsPage — delete', () => {
  async function openDeleteAndConfirm() {
    selectRow(1);
    await waitFor(() => expect(button('Delete')).not.toHaveAttribute('aria-disabled'));
    fireEvent.click(button('Delete'));
    expect(await screen.findByText('Delete Dataset')).toBeInTheDocument();
    expect(screen.getByText(/permanently delete 1 dataset/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Confirmation text'), { target: { value: 'permanently delete' } });
    const confirm = screen.getAllByRole('button', { name: 'Delete' }).find((b) => b.closest('[role="dialog"]'))!;
    fireEvent.click(confirm);
  }

  it('deletes the selected dataset (204) and reloads the list', async () => {
    await renderLoaded();
    datasetsApi.delete.mockResolvedValue(null);
    datasetsApi.list.mockResolvedValue({ datasets: [PRODUCTS] });

    await openDeleteAndConfirm();

    await waitFor(() => expect(datasetsApi.delete).toHaveBeenCalledWith('app-1', 'ds-1'));
    await waitFor(() => expect(screen.queryByText('customers')).toBeNull());
    expect(screen.getByText('products')).toBeInTheDocument();
    expect(screen.queryByText('Delete Dataset')).toBeNull();
    // Selection is cleared, so the selection-based actions are disabled again.
    expect(button('Edit')).toHaveAttribute('aria-disabled', 'true');
  });

  it('on 409 lists the referencing use cases as links and keeps the dataset', async () => {
    await renderLoaded();
    datasetsApi.delete.mockRejectedValue(httpError(409, {
      error: 'dataset is referenced by repeat steps of this application; remove the references first',
      usecases: [{ usecase_id: 'uc-1', name: 'Login as each customer' }, { usecase_id: 'uc-2', name: 'Checkout' }],
    }));

    await openDeleteAndConfirm();

    const alert = await screen.findByTestId('dataset-delete-conflict');
    expect(alert).toHaveTextContent(/"customers".*2 use cases/);
    const link = within(alert).getByRole('link', { name: 'Login as each customer' });
    expect(link).toHaveAttribute('href', '/usecases/uc-1');
    expect(within(alert).getByRole('link', { name: 'Checkout' })).toHaveAttribute('href', '/usecases/uc-2');
    // Dataset stays listed; the list was not reloaded.
    expect(screen.getByText('customers')).toBeInTheDocument();
    expect(datasetsApi.list).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('Delete Dataset')).toBeNull();

    fireEvent.click(link);
    expect(await screen.findByText('usecase page')).toBeInTheDocument();
  });

  it('shows other delete errors in an alert', async () => {
    await renderLoaded();
    datasetsApi.delete.mockRejectedValue(new Error('Server error'));
    await openDeleteAndConfirm();
    expect(await screen.findByText('Server error')).toBeInTheDocument();
    expect(screen.getByText('customers')).toBeInTheDocument();
  });
});

describe('ApplicationDatasetsPage — read-only', () => {
  it('keeps Create / Edit / Delete disabled with a reason, but allows View', async () => {
    mockUsePermissions.mockReturnValue(perms(false, [{ team_id: 'team-a', role: 'editor' }]));
    await renderLoaded();
    datasetsApi.get.mockResolvedValue({ dataset: CUSTOMERS_FULL });

    expect(button('Create dataset')).toHaveAttribute('aria-disabled', 'true');
    selectRow(1);
    await waitFor(() => expect(button('View')).not.toHaveAttribute('aria-disabled'));
    expect(button('Edit')).toHaveAttribute('aria-disabled', 'true');
    expect(button('Delete')).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getAllByText(/Only a team lead of the owning team or an admin can change datasets/).length).toBeGreaterThan(0);

    fireEvent.click(button('View'));
    await waitFor(() => expect(datasetsApi.get).toHaveBeenCalledWith('app-1', 'ds-1'));
    expect(await screen.findByTestId('dataset-view-table')).toBeInTheDocument();
  });
});

describe('ApplicationDatasetsPage — view', () => {
  it('shows the full table read-only, 20 rows per page', async () => {
    await renderLoaded();
    const rows = Array.from({ length: 100 }, (_, i) => [`user${i + 1}@x.test`, i % 2 ? 'admin' : 'viewer']);
    datasetsApi.get.mockResolvedValue({ dataset: { ...CUSTOMERS_FULL, rows } });

    selectRow(1);
    await waitFor(() => expect(button('View')).not.toHaveAttribute('aria-disabled'));
    fireEvent.click(button('View'));

    const view = await screen.findByTestId('dataset-view-table');
    const viewTable = createWrapper(view).findTable()!;
    await waitFor(() => expect(viewTable.findRows()).toHaveLength(20));
    expect(viewTable.findColumnHeaders().map((h) => h.getElement().textContent?.trim())).toEqual(['#', 'email', 'role']);
    expect(within(view).getByText('user1@x.test')).toBeInTheDocument();
    expect(within(view).queryByText('user21@x.test')).toBeNull();
    // Read-only: no inputs in the grid.
    expect(view.querySelectorAll('input')).toHaveLength(0);

    const pagination = createWrapper(view).findPagination()!;
    expect(pagination.findPageNumbers()).toHaveLength(5);
    act(() => { pagination.findNextPageButton().click(); });
    expect(await within(view).findByText('user21@x.test')).toBeInTheDocument();
    expect(within(view).queryByText('user1@x.test')).toBeNull();
  });
});
