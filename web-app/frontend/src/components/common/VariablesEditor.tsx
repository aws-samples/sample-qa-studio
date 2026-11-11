/**
 * VariablesEditor — key/value variables with Save, driven by an API adapter.
 * Shared by the use-case Variables card (`UsecaseVariables`) and the application
 * Variables page (`ApplicationVariablesPage`).
 *
 * Rows whose `source` is `'application'` are inherited: they render in a
 * read-only table with an "Application" badge and are never passed to
 * `api.save`. Every other row (source `'usecase'` or absent) is editable. A
 * use-case row may reuse an inherited key; it then overrides the application
 * value and the editor says so.
 *
 * Mount with `key={id}` so another use case / application starts fresh.
 */
import { useEffect, useMemo, useState } from 'react';
import Alert from '@cloudscape-design/components/alert';
import AttributeEditor from '@cloudscape-design/components/attribute-editor';
import Badge from '@cloudscape-design/components/badge';
import Box from '@cloudscape-design/components/box';
import Button from '@cloudscape-design/components/button';
import Container from '@cloudscape-design/components/container';
import ExpandableSection from '@cloudscape-design/components/expandable-section';
import FormField from '@cloudscape-design/components/form-field';
import Header from '@cloudscape-design/components/header';
import Input from '@cloudscape-design/components/input';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Table, { type TableProps } from '@cloudscape-design/components/table';
import { api as httpApi } from '../../utils/api';
import { ContainerLoading } from './LoadingStates';

export interface VariableRow {
  key: string;
  value: string;
  /** Absent on the application page's own rows; absent means editable. */
  source?: 'application' | 'usecase';
}

export interface VariablesApi {
  list: () => Promise<VariableRow[]>;
  /** Persist the editable rows (inherited rows are already filtered out). */
  save: (rows: VariableRow[]) => Promise<void>;
}

export interface VariablesEditorProps {
  api: VariablesApi;
  /** Render a plain table without any write controls. */
  readOnly?: boolean;
}

/** Mirrors the server-side key pattern and list cap for variables. */
const KEY_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;
const MAX_VARIABLES = 100;

const PREDEFINED_VARIABLES = [
  { key: 'UniqueID', description: 'Random 5-character string' },
  { key: 'Time', description: 'Current timestamp' },
  { key: 'ExecutionID', description: 'Current execution ID' },
  { key: 'CreatedAt', description: 'Execution creation time' },
];

const EMPTY_TEXT = 'No variables configured.';

const isInherited = (row: VariableRow) => row.source === 'application';

/** Error message for the editable rows, or null when they can be saved. */
export function validateVariableRows(rows: VariableRow[]): string | null {
  if (rows.length > MAX_VARIABLES) {
    return `At most ${MAX_VARIABLES} variables are allowed`;
  }
  const keys = rows.map((row) => row.key.trim());
  if (keys.some((key) => !key)) {
    return 'Every variable needs a key';
  }
  const invalid = keys.find((key) => !KEY_PATTERN.test(key));
  if (invalid !== undefined) {
    return `Invalid variable key "${invalid}": use letters, digits and underscores, not starting with a digit`;
  }
  const duplicates = keys.filter((key, index) => keys.indexOf(key) !== index);
  if (duplicates.length > 0) {
    return `Duplicate variable keys found: ${[...new Set(duplicates)].join(', ')}`;
  }
  return null;
}

/**
 * Adapter for a `{variables: [{key, value, source?}]}` endpoint whose POST
 * replaces the list (`usecase/{id}/variables`, `applications/{id}/variables`).
 */
export function variablesApi(path: string): VariablesApi {
  return {
    list: async () => {
      const response = await httpApi.get(path);
      const rows: unknown[] = Array.isArray(response?.variables) ? response.variables : [];
      return rows.map((raw) => {
        const row = (raw ?? {}) as Partial<VariableRow>;
        return {
          key: row.key ?? '',
          value: row.value ?? '',
          ...(row.source === 'application' || row.source === 'usecase' ? { source: row.source } : {}),
        };
      });
    },
    save: async (rows) => {
      await httpApi.post(path, { variables: rows.map(({ key, value }) => ({ key, value })) });
    },
  };
}

function VariablesTable({ rows, showSource }: { rows: VariableRow[]; showSource: boolean }) {
  const columns: TableProps.ColumnDefinition<VariableRow>[] = [
    { id: 'key', header: 'Key', cell: (item) => item.key },
    { id: 'value', header: 'Value', cell: (item) => item.value },
    ...(showSource
      ? [{
          id: 'source',
          header: 'Source',
          cell: (item: VariableRow) => (isInherited(item) ? <Badge>Application</Badge> : 'Use case'),
        }]
      : []),
  ];
  return (
    <Table
      columnDefinitions={columns}
      items={rows}
      trackBy={(item) => `${item.source ?? 'own'}:${item.key}`}
      variant="embedded"
      empty={EMPTY_TEXT}
    />
  );
}

export function VariablesEditor({ api, readOnly = false }: VariablesEditorProps) {
  const [inherited, setInherited] = useState<VariableRow[]>([]);
  const [saved, setSaved] = useState<VariableRow[]>([]);
  const [drafts, setDrafts] = useState<VariableRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await api.list();
      const own = rows.filter((row) => !isInherited(row));
      setInherited(rows.filter(isInherited));
      setSaved(own);
      setDrafts(own);
    } catch (err) {
      console.error('Failed to fetch variables:', err);
      setError('Failed to load variables');
    } finally {
      setLoading(false);
    }
  };

  // Load once per mount; callers remount via `key` when the owner changes.
  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const inheritedKeys = useMemo(() => new Set(inherited.map((row) => row.key)), [inherited]);
  const hasUnsavedChanges = useMemo(() => JSON.stringify(saved) !== JSON.stringify(drafts), [saved, drafts]);

  const handleSave = async () => {
    const rows = drafts.map((row) => ({ ...row, key: row.key.trim() }));
    const invalid = validateVariableRows(rows);
    if (invalid) {
      setError(invalid);
      setSuccess(null);
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await api.save(rows);
      setSaved(rows);
      setDrafts(rows);
      setSuccess('Variables saved');
    } catch (err) {
      console.error('Failed to save variables:', err);
      const detail = err instanceof Error && err.message ? `: ${err.message}` : '';
      setError(`Failed to save variables${detail}`);
    } finally {
      setSaving(false);
    }
  };

  const updateDraft = (index: number, change: Partial<VariableRow>) => {
    setDrafts((rows) => rows.map((row, i) => (i === index ? { ...row, ...change } : row)));
  };

  const clearMessages = () => {
    setError(null);
    setSuccess(null);
  };

  if (loading) {
    return <ContainerLoading title="Variables" text="Loading variables..." />;
  }

  if (readOnly) {
    return (
      <Container>
        <SpaceBetween direction="vertical" size="m">
          {error && <Alert type="error">{error}</Alert>}
          <VariablesTable rows={[...inherited, ...saved]} showSource={inherited.length > 0} />
        </SpaceBetween>
      </Container>
    );
  }

  return (
    <Container
      header={
        <Header
          variant="h2"
          actions={
            <SpaceBetween direction="horizontal" size="xs">
              <Button iconName="refresh" onClick={refresh} disabled={saving} ariaLabel="Refresh variables" />
              {hasUnsavedChanges && (
                <Button variant="link" onClick={() => setDrafts(saved)}>
                  Reset Changes
                </Button>
              )}
              <Button
                variant="primary"
                onClick={handleSave}
                loading={saving}
                disabled={saving || !hasUnsavedChanges}
              >
                {saving ? 'Saving...' : hasUnsavedChanges ? 'Save Changes' : 'Saved'}
              </Button>
            </SpaceBetween>
          }
        />
      }
    >
      <SpaceBetween direction="vertical" size="m">
        {error && (
          <Alert type="error" dismissible onDismiss={clearMessages}>
            {error}
          </Alert>
        )}
        {success && (
          <Alert type="success" dismissible onDismiss={clearMessages}>
            {success}
          </Alert>
        )}

        <ExpandableSection headerText="Predefined Variables">
          <Table
            columnDefinitions={[
              { id: 'key', header: 'Variable', cell: (item) => `{{${item.key}}}` },
              { id: 'description', header: 'Description', cell: (item) => item.description },
            ]}
            items={PREDEFINED_VARIABLES}
            variant="embedded"
          />
        </ExpandableSection>

        {inherited.length > 0 && (
          <SpaceBetween direction="vertical" size="xs">
            <Header
              variant="h3"
              description="Defined on the application. Add a variable with the same key below to override its value for this use case."
            >
              Inherited from application
            </Header>
            <VariablesTable rows={inherited} showSource />
          </SpaceBetween>
        )}

        <AttributeEditor
          onAddButtonClick={() => setDrafts((rows) => [...rows, { key: '', value: '' }])}
          onRemoveButtonClick={({ detail: { itemIndex } }) =>
            setDrafts((rows) => rows.filter((_, i) => i !== itemIndex))
          }
          items={drafts}
          addButtonText="Add new variable"
          removeButtonText="Remove"
          definition={[
            {
              label: 'Key',
              constraintText: (item: VariableRow) =>
                inheritedKeys.has(item.key.trim()) ? 'Overrides application value' : undefined,
              control: (item: VariableRow, itemIndex: number) => (
                <FormField>
                  <Input
                    value={item.key}
                    onChange={({ detail }) => updateDraft(itemIndex, { key: detail.value })}
                    placeholder="Enter key"
                    ariaLabel={`Key ${itemIndex + 1}`}
                  />
                </FormField>
              ),
            },
            {
              label: 'Value',
              control: (item: VariableRow, itemIndex: number) => (
                <FormField>
                  <Input
                    value={item.value}
                    onChange={({ detail }) => updateDraft(itemIndex, { value: detail.value })}
                    placeholder="Enter value"
                    ariaLabel={`Value ${itemIndex + 1}`}
                  />
                </FormField>
              ),
            },
          ]}
          empty={<Box>{EMPTY_TEXT} Click 'Add new variable' to get started.</Box>}
        />
      </SpaceBetween>
    </Container>
  );
}
