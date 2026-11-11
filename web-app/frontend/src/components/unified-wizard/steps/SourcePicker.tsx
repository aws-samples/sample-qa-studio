/**
 * The wizard's "pick a source" step body, shared by SelectSourceStep (clone a
 * use case) and SelectTemplateStep: a searchable Select over a list loaded on
 * mount, then a preview container for the selected item's detail.
 *
 * Each step keeps its own reducer dispatch: `useSourceDetail` hands the loaded
 * detail to `onLoaded`, and only for the selection that is still current.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import FormField from '@cloudscape-design/components/form-field';
import Select, { type SelectProps } from '@cloudscape-design/components/select';
import Box from '@cloudscape-design/components/box';
import Spinner from '@cloudscape-design/components/spinner';
import Alert from '@cloudscape-design/components/alert';
import Badge from '@cloudscape-design/components/badge';
import { api } from '../../../utils/api';

export interface SourceItem {
  id: string;
  name: string;
  description?: string;
}

/**
 * Load `GET path` once and read the list from `response[field]`.
 * `errorFallback` is shown when the error has no message.
 */
export function useSourceList<T extends SourceItem>(path: string, field: string, errorFallback: string) {
  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get(path)
      .then((data) => {
        if (!cancelled) setItems(data?.[field] || []);
      })
      .catch((err) => {
        console.error(`Failed to fetch ${field}:`, err);
        if (!cancelled) setError(err?.message || errorFallback);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path, field, errorFallback]);

  return { items, loading, error, dismissError: () => setError(null) };
}

/**
 * Load the detail of `selectedId` whenever it changes and pass it to
 * `onLoaded`. A response for a selection that is no longer current is
 * dropped. A failed load is logged and leaves the preview empty.
 */
export function useSourceDetail<D>(
  selectedId: string | null,
  fetchDetail: (id: string) => Promise<D>,
  onLoaded: (detail: D) => void,
): boolean {
  const [loading, setLoading] = useState(false);
  // Latest callbacks without re-running the effect on every render.
  const callbacks = useRef({ fetchDetail, onLoaded });
  callbacks.current = { fetchDetail, onLoaded };

  useEffect(() => {
    if (!selectedId) {
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    callbacks.current
      .fetchDetail(selectedId)
      .then((detail) => {
        if (!cancelled) callbacks.current.onLoaded(detail);
      })
      .catch((err) => console.error('Failed to fetch source detail:', err))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  return loading;
}

interface SourcePickerLabels {
  label: string;
  description: string;
  placeholder: string;
  loadingText: string;
  empty: string;
  previewTitle: string;
}

export interface SourcePickerProps<T extends SourceItem> {
  items: T[];
  loading: boolean;
  fetchError: string | null;
  onDismissError: () => void;
  selectedId: string | null;
  onSelect: (item: T | null) => void;
  errorText?: string;
  loadingDetail: boolean;
  /** Preview body for the loaded detail; null while it is not loaded. */
  preview: ReactNode | null;
  labels: SourcePickerLabels;
}

export function SourcePicker<T extends SourceItem>({
  items,
  loading,
  fetchError,
  onDismissError,
  selectedId,
  onSelect,
  errorText,
  loadingDetail,
  preview,
  labels,
}: SourcePickerProps<T>) {
  const options: SelectProps.Option[] = items.map((item) => ({
    label: item.name,
    value: item.id,
    description: item.description,
  }));
  const selectedOption = selectedId ? options.find((opt) => opt.value === selectedId) || null : null;

  return (
    <>
      {fetchError && (
        <Alert type="error" dismissible onDismiss={onDismissError}>
          {fetchError}
        </Alert>
      )}

      <Container>
        <FormField label={labels.label} description={labels.description} errorText={errorText}>
          <Select
            selectedOption={selectedOption}
            onChange={({ detail }) =>
              onSelect(items.find((item) => item.id === detail.selectedOption?.value) || null)
            }
            options={options}
            placeholder={labels.placeholder}
            loadingText={labels.loadingText}
            statusType={loading ? 'loading' : 'finished'}
            disabled={loading}
            filteringType="auto"
            empty={labels.empty}
          />
        </FormField>
      </Container>

      {selectedId && (
        <Container header={<Header variant="h2">{labels.previewTitle}</Header>}>
          {loadingDetail ? (
            <Box textAlign="center" padding="l">
              <Spinner />
            </Box>
          ) : (
            preview
          )}
        </Container>
      )}
    </>
  );
}

/** One key/value cell of a preview grid. */
export function PreviewField({ label, children, wide = false }: { label: string; children: ReactNode; wide?: boolean }) {
  return (
    <div style={wide ? { gridColumn: '1 / -1' } : undefined}>
      <Box variant="awsui-key-label">{label}</Box>
      <div>{children}</div>
    </div>
  );
}

/** Tag badges, or nothing for an empty list. */
export function PreviewTags({ tags }: { tags: string[] }) {
  if (tags.length === 0) return null;
  return (
    <PreviewField label="Tags">
      <SpaceBetween direction="horizontal" size="xs">
        {tags.map((tag) => (
          <Badge key={tag}>{tag}</Badge>
        ))}
      </SpaceBetween>
    </PreviewField>
  );
}

