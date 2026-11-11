/**
 * DatasetFormModal — create or edit one application dataset.
 *
 * FormModal shell + the repeat step's RepeatDatasetEditor (columns, rows,
 * CSV paste), so an application dataset is edited exactly like inline repeat
 * rows. Client validation mirrors the server (`validateRepeatDataset` for the
 * table, the dataset name rule below); the server stays authoritative and its
 * `400 {errors}` list / `409` name conflict are shown in the modal.
 *
 * Mount it only while it is open: the fields are initialised from `dataset`
 * once, on mount.
 */
import { useState } from 'react';
import Alert from '@cloudscape-design/components/alert';
import FormField from '@cloudscape-design/components/form-field';
import Input from '@cloudscape-design/components/input';
import Textarea from '@cloudscape-design/components/textarea';
import FormModal from '../common/FormModal';
import RepeatDatasetEditor from '../usecase/RepeatDatasetEditor';
import { emptyRepeatDataset, validateRepeatDataset, type RepeatDataset } from '../usecase/repeatDatasetArgs';
import { datasetsApi, type ApiHttpError, type ApplicationDataset } from '../../utils/api';

/** Mirrors `DATASET_NAME_PATTERN` / `DATASET_NAME_RULE` in dataset_models.py. */
const DATASET_NAME_RE = /^[A-Za-z_][A-Za-z0-9_ -]{0,63}$/;
const DATASET_NAME_RULE =
  'letters, digits, spaces, underscores and hyphens; must start with a letter or underscore; at most 64 characters';

function datasetNameError(name: string): string | null {
  if (!name) return 'name is required';
  if (!DATASET_NAME_RE.test(name)) return `dataset name "${name}" is invalid (${DATASET_NAME_RULE})`;
  return null;
}

/** Server and client name errors are shown on the Name field; everything else above the fields. */
function isNameError(message: string): boolean {
  return message === 'name is required' || message.startsWith('dataset name "') || message.includes('already exists');
}

interface DatasetFormModalProps {
  visible: boolean;
  applicationId: string;
  /** The dataset to edit (full record); null creates a new one. */
  dataset: ApplicationDataset | null;
  onDismiss: () => void;
  /** Receives the saved dataset as the server returned it. */
  onSaved: (dataset: ApplicationDataset) => void;
}

export default function DatasetFormModal({ visible, applicationId, dataset, onDismiss, onSaved }: DatasetFormModalProps) {
  const [name, setName] = useState(dataset?.name ?? '');
  const [description, setDescription] = useState(dataset?.description ?? '');
  const [table, setTable] = useState<RepeatDataset>(() =>
    dataset ? { columns: dataset.columns, rows: dataset.rows } : emptyRepeatDataset(),
  );
  /** The `errors` list of a server 400, shown one per line. */
  const [serverErrors, setServerErrors] = useState<string[]>([]);

  const reset = () => {
    setName('');
    setDescription('');
    setTable(emptyRepeatDataset());
    setServerErrors([]);
  };

  const handleSubmit = async () => {
    setServerErrors([]);
    const trimmedName = name.trim();
    const nameError = datasetNameError(trimmedName);
    if (nameError) throw new Error(nameError);
    const tableErrors = validateRepeatDataset(table.columns, table.rows);
    if (tableErrors.length > 0) throw new Error(tableErrors.join('; '));

    const body = { name: trimmedName, description: description.trim(), columns: table.columns, rows: table.rows };
    try {
      const response = dataset
        ? await datasetsApi.update(applicationId, dataset.dataset_id, body)
        : await datasetsApi.create(applicationId, body);
      onSaved(response.dataset);
    } catch (err) {
      const errors = (err as Partial<ApiHttpError>).body?.errors;
      setServerErrors(Array.isArray(errors) ? errors.map(String) : []);
      throw err;
    }
  };

  return (
    <FormModal
      visible={visible}
      header={dataset ? 'Edit dataset' : 'Create dataset'}
      submitLabel={dataset ? 'Save' : 'Create'}
      onSubmit={handleSubmit}
      onDismiss={onDismiss}
      onReset={reset}
      errorFallback="Failed to save dataset"
      testIdPrefix="dataset-form"
    >
      {(error) => {
        const nameError = error && isNameError(error) ? error : undefined;
        const generalError = error && !nameError ? error : null;
        return (
          <>
            {generalError && (
              <Alert type="error" data-testid="dataset-form-server-errors">
                {serverErrors.length > 1 ? (
                  <ul style={{ margin: 0, paddingLeft: 20 }}>
                    {serverErrors.map((message) => <li key={message}>{message}</li>)}
                  </ul>
                ) : generalError}
              </Alert>
            )}
            <FormField
              label="Name"
              description="Repeat steps pick the dataset by this name. Unique within the application."
              errorText={nameError}
              data-testid="dataset-form-name-field"
            >
              <Input
                value={name}
                onChange={({ detail }) => setName(detail.value)}
                placeholder="customers"
                data-testid="dataset-form-name-input"
              />
            </FormField>
            <FormField label="Description" description="Optional">
              <Textarea
                value={description}
                onChange={({ detail }) => setDescription(detail.value)}
                placeholder="What the rows represent"
                rows={2}
                data-testid="dataset-form-description-input"
              />
            </FormField>
            <RepeatDatasetEditor columns={table.columns} rows={table.rows} onChange={setTable} />
          </>
        );
      }}
    </FormModal>
  );
}
