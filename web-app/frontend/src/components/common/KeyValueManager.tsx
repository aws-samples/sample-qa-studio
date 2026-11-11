/**
 * KeyValueManager — "Current X" table with Delete plus an "Add New X" editor
 * and Save. Shared by HeadersManager and SecretsManager; each passes an API
 * adapter and labels.
 *
 * `masked` (secrets): the list shows keys only and the value inputs are
 * password fields. Entered values live only in the add-form state, are cleared
 * on a successful save and are never logged or read back.
 *
 * Inherited rows: when `readOnlyRowLabel` is set, rows whose `source` differs
 * from `ownerSource` (e.g. application secrets listed on a use case) render a
 * badge instead of Delete, and a draft with the same key is flagged as an
 * override (the server shadows the inherited entry once saved).
 *
 * `readOnly`: list only — no Save, Delete or add form (viewer on an application).
 *
 * Mount with `key={usecaseId}` so another use case starts with fresh state.
 */
import { useEffect, useState } from 'react';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';
import Badge from '@cloudscape-design/components/badge';
import AttributeEditor from '@cloudscape-design/components/attribute-editor';
import Input from '@cloudscape-design/components/input';
import FormField from '@cloudscape-design/components/form-field';
import Alert from '@cloudscape-design/components/alert';
import Table, { type TableProps } from '@cloudscape-design/components/table';
import Box from '@cloudscape-design/components/box';

/** A configured entry; `value` is absent when the API does not return it (secrets). */
export interface KeyValueItem {
  key: string;
  value?: string;
  /** Where the entry is defined (`usecase` / `application`); absent when the API has one layer. */
  source?: string;
}

/** A row of the add form. */
export interface KeyValueDraft {
  key: string;
  value: string;
}

export interface KeyValueApi {
  list: () => Promise<KeyValueItem[]>;
  /** Persist the new rows; `existing` is the list currently shown. */
  save: (drafts: KeyValueDraft[], existing: KeyValueItem[]) => Promise<void>;
  /** Delete one key; `existing` is the list currently shown. */
  remove: (key: string, existing: KeyValueItem[]) => Promise<void>;
}

export interface KeyValueLabels {
  /** "header" / "secret" */
  singular: string;
  /** "headers" / "secrets" */
  plural: string;
  /** "Header" / "Secret" */
  singularTitle: string;
  /** "Headers" / "Secrets" */
  pluralTitle: string;
  description: string;
  keyLabel: string;
  valueLabel: string;
  keyPlaceholder: string;
  valuePlaceholder: string;
  /** Shown instead of the table when the list is empty. */
  emptyText: string;
}

export interface KeyValueManagerProps {
  api: KeyValueApi;
  labels: KeyValueLabels;
  masked: boolean;
  /** `source` of the rows this manager owns; rows with another source are inherited. */
  ownerSource?: string;
  /** Badge text for inherited rows; without it every row is editable. */
  readOnlyRowLabel?: string;
  /** List only, no write controls. */
  readOnly?: boolean;
}

/** Error message for the add form, or null when it can be saved. */
export function validateDrafts(drafts: KeyValueDraft[], labels: KeyValueLabels): string | null {
  if (drafts.length === 0) {
    return `Please add at least one ${labels.singular}`;
  }
  if (drafts.some((d) => !d.key.trim() || !d.value.trim())) {
    return `All ${labels.plural} must have both a key and value`;
  }
  const keys = drafts.map((d) => d.key.trim());
  const duplicates = keys.filter((key, index) => keys.indexOf(key) !== index);
  if (duplicates.length > 0) {
    return `Duplicate ${labels.singular} keys found: ${duplicates.join(', ')}`;
  }
  return null;
}

export function KeyValueManager({
  api,
  labels,
  masked,
  ownerSource,
  readOnlyRowLabel,
  readOnly = false,
}: KeyValueManagerProps) {
  const [drafts, setDrafts] = useState<KeyValueDraft[]>([]);
  const [existing, setExisting] = useState<KeyValueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      setExisting(await api.list());
    } catch (err) {
      console.error(`Failed to fetch ${labels.plural}:`, err);
      setError(`Failed to load ${labels.plural}`);
    } finally {
      setLoading(false);
    }
  };

  // Load once per mount; callers remount via `key` when the use case changes.
  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSave = async () => {
    const invalid = validateDrafts(drafts, labels);
    if (invalid) {
      setError(invalid);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.save(drafts, existing);
      setSuccess(`${labels.pluralTitle} saved successfully`);
      setDrafts([]);
      await refresh();
    } catch (err) {
      console.error(`Failed to save ${labels.plural}:`, err);
      setError(`Failed to save ${labels.plural}`);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (key: string) => {
    setDeleting(key);
    setError(null);
    try {
      await api.remove(key, existing);
      setSuccess(`${labels.singularTitle} "${key}" deleted successfully`);
      await refresh();
    } catch (err) {
      console.error(`Failed to delete ${labels.singular}:`, err);
      setError(`Failed to delete ${labels.singular} "${key}"`);
    } finally {
      setDeleting(null);
    }
  };

  const updateDraft = (index: number, change: Partial<KeyValueDraft>) => {
    setDrafts((rows) => rows.map((row, i) => (i === index ? { ...row, ...change } : row)));
  };

  const clearMessages = () => {
    setError(null);
    setSuccess(null);
  };

  const isInherited = (item: KeyValueItem) =>
    readOnlyRowLabel !== undefined && item.source !== undefined && item.source !== ownerSource;
  const inheritedKeys = new Set(existing.filter(isInherited).map((item) => item.key));
  const overriddenKeys = drafts.map((d) => d.key.trim()).filter((key) => inheritedKeys.has(key));

  const columns: TableProps.ColumnDefinition<KeyValueItem>[] = [
    {
      id: 'key',
      header: labels.keyLabel,
      cell: (item) =>
        isInherited(item) ? (
          <SpaceBetween direction="horizontal" size="xs">
            <span>{item.key}</span>
            <Badge color="blue">{readOnlyRowLabel}</Badge>
          </SpaceBetween>
        ) : (
          item.key
        ),
    },
    ...(masked ? [] : [{ id: 'value', header: labels.valueLabel, cell: (item: KeyValueItem) => item.value }]),
    ...(readOnly
      ? []
      : [
          {
            id: 'actions',
            header: 'Actions',
            cell: (item: KeyValueItem) =>
              isInherited(item) ? null : (
                <Button variant="link" loading={deleting === item.key} onClick={() => handleDelete(item.key)}>
                  Delete
                </Button>
              ),
          },
        ]),
  ];

  return (
    <Container
      header={
        <Header
          variant="h2"
          description={labels.description}
          actions={
            readOnly ? undefined : (
              <Button
                variant="primary"
                onClick={handleSave}
                loading={saving}
                disabled={saving || drafts.length === 0}
              >
                {saving ? 'Saving...' : `Save ${labels.pluralTitle}`}
              </Button>
            )
          }
        />
      }
    >
      <SpaceBetween direction="vertical" size="l">
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

        <Header variant="h3">Current {labels.pluralTitle}</Header>
        {loading ? (
          <Box>Loading {labels.plural}...</Box>
        ) : existing.length === 0 ? (
          <Box>{labels.emptyText}</Box>
        ) : (
          <Table columnDefinitions={columns} items={existing} trackBy="key" />
        )}

        {!readOnly && (
          <>
            <Header variant="h3">Add New {labels.pluralTitle}</Header>
            {overriddenKeys.length > 0 && (
              <Alert type="info" data-testid="override-hint">
                {overriddenKeys.map((key) => (
                  <div key={key}>
                    Saving "{key}" overrides the {readOnlyRowLabel} {labels.singular} of the same name here.
                  </div>
                ))}
              </Alert>
            )}
            <AttributeEditor
              onAddButtonClick={() => setDrafts((rows) => [...rows, { key: '', value: '' }])}
              onRemoveButtonClick={({ detail: { itemIndex } }) =>
                setDrafts((rows) => rows.filter((_, i) => i !== itemIndex))
              }
              items={drafts}
              addButtonText={`Add new ${labels.singular}`}
              removeButtonText="Remove"
              definition={[
                {
                  label: labels.keyLabel,
                  control: (item: KeyValueDraft, itemIndex: number) => (
                    <FormField>
                      <Input
                        value={item.key}
                        onChange={({ detail }) => updateDraft(itemIndex, { key: detail.value })}
                        placeholder={labels.keyPlaceholder}
                        ariaLabel={`${labels.keyLabel} ${itemIndex + 1}`}
                      />
                    </FormField>
                  ),
                },
                {
                  label: labels.valueLabel,
                  control: (item: KeyValueDraft, itemIndex: number) => (
                    <FormField>
                      <Input
                        type={masked ? 'password' : 'text'}
                        value={item.value}
                        onChange={({ detail }) => updateDraft(itemIndex, { value: detail.value })}
                        placeholder={labels.valuePlaceholder}
                        ariaLabel={`${labels.valueLabel} ${itemIndex + 1}`}
                      />
                    </FormField>
                  ),
                },
              ]}
            />
          </>
        )}
      </SpaceBetween>
    </Container>
  );
}
