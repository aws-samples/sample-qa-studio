/**
 * ApplicationDatasetsPage — the application's named datasets (columns + rows)
 * that repeat steps of its use cases reference through `dataset_id`.
 *
 * Inside the ApplicationConfigPage shell: a Cloudscape Table of dataset
 * summaries with a name filter and selection-based header actions (View,
 * Edit, Delete, Create dataset). Create / Edit open DatasetFormModal with the
 * full record; View shows the rows read-only, 20 per page. Delete goes through
 * the typed DeleteConfirmModal; a `409` lists the referencing use cases as
 * links and leaves the dataset in place.
 *
 * Modals are mounted only while open: Cloudscape renders a hidden Modal's
 * buttons into the DOM, which the read-only page must not expose.
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Alert from '@cloudscape-design/components/alert';
import Box from '@cloudscape-design/components/box';
import Button from '@cloudscape-design/components/button';
import Header from '@cloudscape-design/components/header';
import Link from '@cloudscape-design/components/link';
import Modal from '@cloudscape-design/components/modal';
import Pagination from '@cloudscape-design/components/pagination';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Table from '@cloudscape-design/components/table';
import TextFilter from '@cloudscape-design/components/text-filter';
import ApplicationConfigPage from './ApplicationConfigPage';
import DatasetFormModal from './DatasetFormModal';
import DeleteConfirmModal from '../common/DeleteConfirmModal';
import { formatDateTime } from '../../utils/dateFormat';
import {
  datasetsApi,
  type ApiHttpError,
  type ApplicationDataset,
  type ApplicationDatasetSummary,
} from '../../utils/api';

const READ_ONLY_REASON = 'Only a team lead of the owning team or an admin can change datasets.';
const SELECT_FIRST_REASON = 'Select a dataset first';
const VIEW_PAGE_SIZE = 20;

interface ReferencingUsecase {
  usecase_id: string;
  name: string;
}

/** The 409 answer of a delete: the dataset and the repeat-step owners that still reference it. */
interface DeleteConflict {
  dataset: ApplicationDatasetSummary;
  usecases: ReferencingUsecase[];
}

const errorMessage = (err: unknown, fallback: string) =>
  (err as { message?: string } | null)?.message || fallback;

/** Named datasets of the application that repeat steps can reference instead of inline rows. */
export default function ApplicationDatasetsPage() {
  return (
    <ApplicationConfigPage
      title="Datasets"
      description="Named tables of test data that repeat steps of this application's use cases can reference instead of carrying their own rows."
    >
      {({ application, readOnly }) => <DatasetsTable applicationId={application.id} readOnly={readOnly} />}
    </ApplicationConfigPage>
  );
}

interface DatasetsTableProps {
  applicationId: string;
  readOnly: boolean;
}

function DatasetsTable({ applicationId, readOnly }: DatasetsTableProps) {
  const navigate = useNavigate();
  const [datasets, setDatasets] = useState<ApplicationDatasetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [selected, setSelected] = useState<ApplicationDatasetSummary | null>(null);
  const [filteringText, setFilteringText] = useState('');

  /** `{ dataset: null }` = create; a full record = edit. Absent = closed. */
  const [form, setForm] = useState<{ dataset: ApplicationDataset | null } | null>(null);
  const [viewing, setViewing] = useState<ApplicationDataset | null>(null);
  const [fetching, setFetching] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteConflict, setDeleteConflict] = useState<DeleteConflict | null>(null);
  const [actionError, setActionError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      const response = await datasetsApi.list(applicationId);
      setDatasets(response.datasets || []);
    } catch (err) {
      setLoadError(errorMessage(err, 'Failed to load datasets'));
    } finally {
      setLoading(false);
    }
  }, [applicationId]);

  useEffect(() => {
    load();
  }, [load]);

  /** Fetch the full record of the selected dataset for Edit / View. */
  const loadSelected = async (onLoaded: (dataset: ApplicationDataset) => void) => {
    if (!selected) return;
    setFetching(true);
    setActionError('');
    try {
      const response = await datasetsApi.get(applicationId, selected.dataset_id);
      onLoaded(response.dataset);
    } catch (err) {
      setActionError(errorMessage(err, 'Failed to load dataset'));
    } finally {
      setFetching(false);
    }
  };

  const handleSaved = () => {
    setSelected(null);
    load();
  };

  const handleDelete = async () => {
    if (!selected) return;
    const target = selected;
    setDeleting(true);
    setActionError('');
    setDeleteConflict(null);
    try {
      await datasetsApi.delete(applicationId, target.dataset_id);
      setConfirmDelete(false);
      setSelected(null);
      load();
    } catch (err) {
      setConfirmDelete(false);
      const http = err as Partial<ApiHttpError>;
      if (http.status === 409 && Array.isArray(http.body?.usecases)) {
        setDeleteConflict({ dataset: target, usecases: http.body.usecases as ReferencingUsecase[] });
      } else {
        setActionError(errorMessage(err, 'Failed to delete dataset'));
      }
    } finally {
      setDeleting(false);
    }
  };

  const searchText = filteringText.trim().toLowerCase();
  const filteredItems = searchText
    ? datasets.filter((dataset) => dataset.name.toLowerCase().includes(searchText))
    : datasets;

  const selectionReason = selected ? undefined : SELECT_FIRST_REASON;
  const writeReason = readOnly ? READ_ONLY_REASON : selectionReason;

  return (
    <SpaceBetween size="m">
      {loadError && <Alert type="error" header="Error">{loadError}</Alert>}
      {actionError && (
        <Alert type="error" dismissible onDismiss={() => setActionError('')}>
          {actionError}
        </Alert>
      )}
      {deleteConflict && (
        <Alert
          type="warning"
          dismissible
          onDismiss={() => setDeleteConflict(null)}
          header="Dataset is still in use"
          data-testid="dataset-delete-conflict"
        >
          <SpaceBetween size="xs">
            <Box>
              The dataset &quot;{deleteConflict.dataset.name}&quot; is referenced by repeat steps of{' '}
              {deleteConflict.usecases.length} use case{deleteConflict.usecases.length === 1 ? '' : 's'}.
              Switch those steps to inline rows or another dataset, then delete it.
            </Box>
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {deleteConflict.usecases.map((usecase) => (
                <li key={usecase.usecase_id}>
                  <Link
                    href={`/usecases/${usecase.usecase_id}`}
                    onFollow={(event) => { event.preventDefault(); navigate(`/usecases/${usecase.usecase_id}`); }}
                  >
                    {usecase.name}
                  </Link>
                </li>
              ))}
            </ul>
          </SpaceBetween>
        </Alert>
      )}

      <Table
        columnDefinitions={[
          { id: 'name', header: 'Name', cell: (item: ApplicationDatasetSummary) => item.name, isRowHeader: true },
          {
            id: 'description',
            header: 'Description',
            cell: (item: ApplicationDatasetSummary) => item.description || <Box color="text-status-inactive">-</Box>,
          },
          { id: 'columns', header: 'Columns', cell: (item: ApplicationDatasetSummary) => item.column_count, width: 110 },
          { id: 'rows', header: 'Rows', cell: (item: ApplicationDatasetSummary) => item.row_count, width: 100 },
          { id: 'updated', header: 'Updated', cell: (item: ApplicationDatasetSummary) => formatDateTime(item.updated_at), width: 190 },
        ]}
        items={filteredItems}
        trackBy="dataset_id"
        loading={loading}
        loadingText="Loading datasets..."
        selectionType="single"
        selectedItems={selected ? [selected] : []}
        onSelectionChange={({ detail }) => setSelected(detail.selectedItems[0] ?? null)}
        ariaLabels={{
          selectionGroupLabel: 'Dataset selection',
          itemSelectionLabel: (_, item) => `Select ${item.name}`,
        }}
        header={
          <Header
            counter={`(${datasets.length})`}
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                <Button
                  disabled={!selected || fetching}
                  disabledReason={selectionReason}
                  loading={fetching}
                  onClick={() => loadSelected(setViewing)}
                >
                  View
                </Button>
                <Button
                  disabled={readOnly || !selected || fetching}
                  disabledReason={writeReason}
                  onClick={() => loadSelected((dataset) => setForm({ dataset }))}
                >
                  Edit
                </Button>
                <Button
                  disabled={readOnly || !selected}
                  disabledReason={writeReason}
                  onClick={() => { setDeleteConflict(null); setConfirmDelete(true); }}
                >
                  Delete
                </Button>
                <Button
                  variant="primary"
                  disabled={readOnly}
                  disabledReason={readOnly ? READ_ONLY_REASON : undefined}
                  onClick={() => setForm({ dataset: null })}
                >
                  Create dataset
                </Button>
              </SpaceBetween>
            }
          >
            Datasets
          </Header>
        }
        filter={
          <TextFilter
            filteringText={filteringText}
            onChange={({ detail }) => setFilteringText(detail.filteringText)}
            filteringPlaceholder="Find datasets by name"
            countText={`${filteredItems.length} ${filteredItems.length === 1 ? 'match' : 'matches'}`}
          />
        }
        empty={
          <Box textAlign="center" color="inherit" padding="l">
            <SpaceBetween size="xs">
              <b>No datasets</b>
              <Box variant="p" color="inherit">
                {filteringText ? `No datasets match "${filteringText}"` : 'This application has no datasets yet.'}
              </Box>
            </SpaceBetween>
          </Box>
        }
      />

      {form && (
        <DatasetFormModal
          visible
          applicationId={applicationId}
          dataset={form.dataset}
          onDismiss={() => setForm(null)}
          onSaved={handleSaved}
        />
      )}

      {viewing && <DatasetViewModal dataset={viewing} onDismiss={() => setViewing(null)} />}

      {confirmDelete && (
        <DeleteConfirmModal
          visible
          count={1}
          noun={{ singular: 'dataset', plural: 'datasets', title: 'Dataset' }}
          consequences="Repeat steps of this application's use cases can no longer reference it; the deletion is refused while any step still does."
          onConfirm={handleDelete}
          onDismiss={() => setConfirmDelete(false)}
          loading={deleting}
        />
      )}
    </SpaceBetween>
  );
}

interface DatasetViewModalProps {
  dataset: ApplicationDataset;
  onDismiss: () => void;
}

interface ViewRow {
  index: number;
  cells: string[];
}

/** Read-only view of the whole table, paginated so 100-row datasets stay readable. */
function DatasetViewModal({ dataset, onDismiss }: DatasetViewModalProps) {
  const [page, setPage] = useState(1);
  const pagesCount = Math.max(1, Math.ceil(dataset.rows.length / VIEW_PAGE_SIZE));
  const start = (page - 1) * VIEW_PAGE_SIZE;
  const items: ViewRow[] = dataset.rows
    .slice(start, start + VIEW_PAGE_SIZE)
    .map((cells, offset) => ({ index: start + offset + 1, cells }));

  return (
    <Modal
      visible
      size="large"
      onDismiss={onDismiss}
      header={dataset.name}
      footer={
        <Box float="right">
          <Button variant="primary" onClick={onDismiss}>Close</Button>
        </Box>
      }
    >
      <div data-testid="dataset-view-table">
        <Table
          variant="embedded"
          columnDefinitions={[
            { id: 'index', header: '#', cell: (row: ViewRow) => row.index, width: 70 },
            ...dataset.columns.map((column, columnIndex) => ({
              id: `col-${columnIndex}`,
              header: column,
              cell: (row: ViewRow) => row.cells[columnIndex] ?? '',
            })),
          ]}
          items={items}
          trackBy={(row) => String(row.index)}
          header={
            <Header
              variant="h3"
              description={dataset.description || undefined}
              counter={`(${dataset.rows.length})`}
            >
              Rows
            </Header>
          }
          pagination={
            <Pagination
              currentPageIndex={page}
              pagesCount={pagesCount}
              onChange={({ detail }) => setPage(detail.currentPageIndex)}
            />
          }
          empty={<Box textAlign="center" color="inherit">No rows</Box>}
        />
      </div>
    </Modal>
  );
}
