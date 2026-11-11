import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { TableProps } from '@cloudscape-design/components';

const navigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useNavigate: () => navigate,
}));

import {
  AddItemsPicker,
  NAVIGATE_BACK_MS,
  PickerNameCell,
  type AddItemsPickerProps,
} from '../AddItemsPicker';

interface Item {
  id: string;
  name: string;
  added?: boolean;
}

const ITEMS: Item[] = [
  { id: 'a', name: 'Alpha' },
  { id: 'b', name: 'Beta', added: true },
  { id: 'c', name: 'Gamma' },
];

const columns: TableProps.ColumnDefinition<Item>[] = [
  {
    id: 'name',
    header: 'Name',
    cell: (item) => (
      <PickerNameCell name={item.name} href={`/x/${item.id}`} alreadyAddedLabel={item.added ? 'Already in target' : undefined} />
    ),
  },
];

function renderPicker(overrides: Partial<AddItemsPickerProps<Item>> = {}) {
  const props: AddItemsPickerProps<Item> = {
    backHref: '/targets/t1',
    breadcrumbs: (name) => [{ text: 'Home', href: '/' }, { text: name || 'Loading...' }],
    fetchTargetName: vi.fn().mockResolvedValue('Target One'),
    fetchCandidates: vi.fn().mockResolvedValue(ITEMS),
    columnDefinitions: columns,
    getId: (item) => item.id,
    isAlreadyAdded: (item) => Boolean(item.added),
    matchesSearch: (item, text) => item.name.toLowerCase().includes(text),
    onSubmit: vi.fn().mockResolvedValue('Added 1 item'),
    labels: {
      title: 'Add Items to Target',
      description: (name) => `Select items to add to "${name || 'this target'}"`,
      availableTitle: 'Available Items',
      loadingText: 'Loading items...',
      filterPlaceholder: 'Search items',
      empty: 'No items found',
      noMatches: (text) => `No items match "${text}"`,
      targetLoadError: 'Failed to fetch target',
      candidatesLoadError: 'Failed to fetch items',
      submitError: 'Failed to add items',
    },
    ...overrides,
  };
  render(
    <MemoryRouter>
      <AddItemsPicker<Item> {...props} />
    </MemoryRouter>,
  );
  return props;
}

const rowOf = (name: string) => screen.getByText(name).closest('tr') as HTMLElement;
const checkboxOf = (name: string) => within(rowOf(name)).getByRole('checkbox');
const addButton = () => screen.getByRole('button', { name: /Add Selected/ });

beforeEach(() => {
  navigate.mockReset();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('AddItemsPicker — loading', () => {
  it('shows the loading container, then the candidates and the target name', async () => {
    renderPicker();
    expect(screen.getByText('Loading items...')).toBeInTheDocument();

    expect(await screen.findByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('Gamma')).toBeInTheDocument();
    expect(screen.getByText('Add Items to Target')).toBeInTheDocument();
    expect(screen.getByText('Select items to add to "Target One"')).toBeInTheDocument();
  });

  it('shows the empty state when there are no candidates', async () => {
    renderPicker({ fetchCandidates: vi.fn().mockResolvedValue([]) });
    expect(await screen.findByText('No items found')).toBeInTheDocument();
  });

  it('shows a candidate load error with the fallback message', async () => {
    renderPicker({ fetchCandidates: vi.fn().mockRejectedValue({}) });
    expect(await screen.findByText('Failed to fetch items')).toBeInTheDocument();
    expect(screen.getByText('No items found')).toBeInTheDocument();
  });

  it('shows the target load error message and the fallback description', async () => {
    renderPicker({ fetchTargetName: vi.fn().mockRejectedValue(new Error('Target gone')) });
    expect(await screen.findByText('Target gone')).toBeInTheDocument();
    expect(screen.getByText('Select items to add to "this target"')).toBeInTheDocument();
  });

  it('lists only visible candidates', async () => {
    renderPicker({ isCandidateVisible: (item) => item.id !== 'c' });
    expect(await screen.findByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('Beta')).toBeInTheDocument();
    expect(screen.queryByText('Gamma')).not.toBeInTheDocument();
  });
});

describe('AddItemsPicker — search', () => {
  it('filters by the lower-cased search text and shows the no-match state', async () => {
    const props = renderPicker({ matchesSearch: vi.fn((item: Item, text: string) => item.name.toLowerCase().includes(text)) });
    await screen.findByText('Alpha');

    fireEvent.change(screen.getByPlaceholderText('Search items'), { target: { value: 'GAM' } });
    expect(screen.getByText('Gamma')).toBeInTheDocument();
    expect(screen.queryByText('Alpha')).not.toBeInTheDocument();
    // Cloudscape renders the count twice (visible + live region).
    expect(screen.getAllByText('1 match').length).toBeGreaterThan(0);
    expect(props.matchesSearch).toHaveBeenCalledWith(expect.anything(), 'gam');

    fireEvent.change(screen.getByPlaceholderText('Search items'), { target: { value: 'zzz' } });
    expect(screen.getByText('No items match "zzz"')).toBeInTheDocument();
  });
});

describe('AddItemsPicker — already added', () => {
  it('disables the rows already in the target and shows their badge', async () => {
    renderPicker();
    await screen.findByText('Beta');
    expect(checkboxOf('Beta')).toBeDisabled();
    expect(checkboxOf('Alpha')).not.toBeDisabled();
    expect(within(rowOf('Beta')).getByText('Already in target')).toBeInTheDocument();
    expect(within(rowOf('Alpha')).queryByText('Already in target')).not.toBeInTheDocument();
  });
});

describe('AddItemsPicker — submit', () => {
  it('disables Add Selected until something is selected', async () => {
    renderPicker();
    await screen.findByText('Alpha');
    expect(addButton()).toBeDisabled();
    expect(addButton()).toHaveTextContent('Add Selected (0)');
  });

  it('submits the multi-selection, shows the message and navigates back', async () => {
    const props = renderPicker();
    await screen.findByText('Alpha');
    fireEvent.click(checkboxOf('Alpha'));
    fireEvent.click(checkboxOf('Gamma'));
    expect(addButton()).toHaveTextContent('Add Selected (2)');

    vi.useFakeTimers();
    await act(async () => {
      fireEvent.click(addButton());
    });
    expect(props.onSubmit).toHaveBeenCalledWith([ITEMS[0], ITEMS[2]]);
    expect(screen.getByText('Added 1 item')).toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(NAVIGATE_BACK_MS);
    });
    expect(navigate).toHaveBeenCalledWith('/targets/t1');
  });

  it('shows the submit error and stays on the page', async () => {
    renderPicker({ onSubmit: vi.fn().mockRejectedValue(new Error('Quota exceeded')) });
    await screen.findByText('Alpha');
    fireEvent.click(checkboxOf('Alpha'));
    fireEvent.click(addButton());

    expect(await screen.findByText('Quota exceeded')).toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();
    await waitFor(() => expect(addButton()).not.toBeDisabled());
  });

  it('falls back to the submit error label', async () => {
    renderPicker({ onSubmit: vi.fn().mockRejectedValue({}) });
    await screen.findByText('Alpha');
    fireEvent.click(checkboxOf('Alpha'));
    fireEvent.click(addButton());
    expect(await screen.findByText('Failed to add items')).toBeInTheDocument();
  });

  it('Cancel navigates back', async () => {
    renderPicker();
    await screen.findByText('Alpha');
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(navigate).toHaveBeenCalledWith('/targets/t1');
  });
});
