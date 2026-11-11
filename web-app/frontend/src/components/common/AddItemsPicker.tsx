/**
 * AddItemsPicker — the "Add X to Y" page: a searchable multi-select table of
 * candidates where items already in the target are disabled, plus Cancel /
 * "Add Selected (n)". On success it shows the message returned by `onSubmit`
 * and navigates back to `backHref`.
 *
 * Used by AddUsecasesToSuite, AddUsecasesToApplication and
 * AddTestSuitesToApplication; each passes its fetchers, columns and labels.
 * Mount it with `key={targetId}` so a new target starts with fresh state.
 */
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Badge,
  Button,
  Header,
  Link,
  SpaceBetween,
  Table,
  TextFilter,
  type TableProps,
} from '@cloudscape-design/components';
import { ErrorState } from '../../utils/errorManager';
import { ContainerLoading } from './LoadingStates';
import Breadcrumb from './Breadcrumb';

/** Alerts disappear after this long. */
const ALERT_DISMISS_MS = 5000;
/** Delay between the success alert and navigating back. */
export const NAVIGATE_BACK_MS = 1500;

interface PickerBreadcrumb {
  text: string;
  href?: string;
}

interface AddItemsPickerLabels {
  /** Page heading, e.g. "Add Use Cases to Suite". */
  title: string;
  /** Header description, given the target's name once loaded. */
  description: (targetName?: string) => string;
  /** Title of the loading container, e.g. "Available Use Cases". */
  availableTitle: string;
  /** e.g. "Loading use cases..." */
  loadingText: string;
  filterPlaceholder: string;
  /** Empty table without a filter, e.g. "No use cases found". */
  empty: string;
  /** Empty table with a filter. */
  noMatches: (filteringText: string) => string;
  /** Fallbacks when an error carries no message. */
  targetLoadError: string;
  candidatesLoadError: string;
  submitError: string;
}

export interface AddItemsPickerProps<T> {
  /** Cancel and post-success navigation target, e.g. `/test-suites/{id}`. */
  backHref: string;
  breadcrumbs: (targetName?: string) => PickerBreadcrumb[];
  /** Name of the suite/application items are added to. */
  fetchTargetName: () => Promise<string | undefined>;
  fetchCandidates: () => Promise<T[]>;
  /** Only candidates passing this are listed (e.g. team scoping). Default: all. */
  isCandidateVisible?: (item: T) => boolean;
  columnDefinitions: TableProps.ColumnDefinition<T>[];
  getId: (item: T) => string;
  /** Already-added rows are listed but cannot be selected. */
  isAlreadyAdded: (item: T) => boolean;
  /** `searchText` is lower-cased and non-empty. */
  matchesSearch: (item: T, searchText: string) => boolean;
  /** Add the selection; resolves to the success message. */
  onSubmit: (selected: T[]) => Promise<string>;
  labels: AddItemsPickerLabels;
}

function errorMessage(err: unknown, fallback: string): string {
  return (err as ErrorState | null)?.message || fallback;
}

export function AddItemsPicker<T>({
  backHref,
  breadcrumbs,
  fetchTargetName,
  fetchCandidates,
  isCandidateVisible,
  columnDefinitions,
  getId,
  isAlreadyAdded,
  matchesSearch,
  onSubmit,
  labels,
}: AddItemsPickerProps<T>) {
  const navigate = useNavigate();
  const [targetName, setTargetName] = useState<string | undefined>();
  const [candidates, setCandidates] = useState<T[]>([]);
  const [loadingTarget, setLoadingTarget] = useState(true);
  const [loadingCandidates, setLoadingCandidates] = useState(true);
  const [adding, setAdding] = useState(false);
  const [selectedItems, setSelectedItems] = useState<T[]>([]);
  const [filteringText, setFilteringText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const navigateTimer = useRef<ReturnType<typeof setTimeout>>();

  // Load once per mount; callers remount via `key` when the target changes.
  useEffect(() => {
    let cancelled = false;
    fetchTargetName()
      .then((name) => { if (!cancelled) setTargetName(name); })
      .catch((err) => { if (!cancelled) setError(errorMessage(err, labels.targetLoadError)); })
      .finally(() => { if (!cancelled) setLoadingTarget(false); });
    fetchCandidates()
      .then((items) => { if (!cancelled) setCandidates(items); })
      .catch((err) => { if (!cancelled) setError(errorMessage(err, labels.candidatesLoadError)); })
      .finally(() => { if (!cancelled) setLoadingCandidates(false); });
    return () => {
      cancelled = true;
      clearTimeout(navigateTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!error && !success) return undefined;
    const timer = setTimeout(() => {
      setError(null);
      setSuccess(null);
    }, ALERT_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [error, success]);

  const handleSubmit = async () => {
    setAdding(true);
    try {
      setSuccess(await onSubmit(selectedItems));
      navigateTimer.current = setTimeout(() => navigate(backHref), NAVIGATE_BACK_MS);
    } catch (err) {
      setError(errorMessage(err, labels.submitError));
    } finally {
      setAdding(false);
    }
  };

  const searchText = filteringText.toLowerCase();
  const visible = isCandidateVisible ? candidates.filter(isCandidateVisible) : candidates;
  const filtered = searchText ? visible.filter((item) => matchesSearch(item, searchText)) : visible;

  return (
    <SpaceBetween direction="vertical" size="l">
      <Breadcrumb items={breadcrumbs(targetName)} />

      {error && (
        <Alert type="error" dismissible onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert type="success" dismissible onDismiss={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      <Header
        variant="h1"
        description={labels.description(targetName)}
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            <Button onClick={() => navigate(backHref)} disabled={adding}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleSubmit}
              loading={adding}
              disabled={adding || selectedItems.length === 0}
            >
              Add Selected ({selectedItems.length})
            </Button>
          </SpaceBetween>
        }
      >
        {labels.title}
      </Header>

      {loadingCandidates || loadingTarget ? (
        <ContainerLoading title={labels.availableTitle} text={labels.loadingText} />
      ) : (
        <Table
          columnDefinitions={columnDefinitions}
          items={filtered}
          trackBy={getId}
          empty={filteringText ? labels.noMatches(filteringText) : labels.empty}
          filter={
            <TextFilter
              filteringText={filteringText}
              onChange={({ detail }) => setFilteringText(detail.filteringText)}
              filteringPlaceholder={labels.filterPlaceholder}
              countText={`${filtered.length} ${filtered.length === 1 ? 'match' : 'matches'}`}
            />
          }
          selectionType="multi"
          selectedItems={selectedItems}
          onSelectionChange={({ detail }) => setSelectedItems(detail.selectedItems)}
          isItemDisabled={isAlreadyAdded}
          resizableColumns
        />
      )}
    </SpaceBetween>
  );
}

interface PickerNameCellProps {
  name: string;
  href: string;
  description?: string;
  /** Badge text shown when the item is already in the target, e.g. "Already in suite". */
  alreadyAddedLabel?: string;
}

/** Name column cell: external link, description, "Already in …" badge. */
export function PickerNameCell({ name, href, description, alreadyAddedLabel }: PickerNameCellProps) {
  return (
    <div>
      <Link href={href} external>
        {name}
      </Link>
      {description && (
        <div style={{ fontSize: '0.85em', color: '#5f6b7a', marginTop: '4px', whiteSpace: 'pre-line' }}>
          {description}
        </div>
      )}
      {alreadyAddedLabel && (
        <div style={{ marginTop: '4px' }}>
          <Badge color="green">{alreadyAddedLabel}</Badge>
        </div>
      )}
    </div>
  );
}
