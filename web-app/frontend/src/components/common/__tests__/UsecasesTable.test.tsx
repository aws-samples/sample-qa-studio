import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { UsecasesTable, UsecaseItem } from '../UsecasesTable';

// Mock dateFormat utility
vi.mock('../../../utils/dateFormat', () => ({
  formatDateTime: (ts: string) => ts,
}));

describe('UsecasesTable', () => {
  const createItem = (overrides: Partial<UsecaseItem> = {}): UsecaseItem => ({
    id: 'uc-1',
    name: 'Login Test',
    description: 'Tests login flow',
    active: true,
    tags: ['smoke'],
    last_execution_status: 'success',
    last_execution_time: '2026-01-15T10:00:00Z',
    test_platform: 'web',
    ...overrides,
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders items with name, status, and platform badge', () => {
    const items = [
      createItem({ id: 'uc-1', name: 'Login Test', test_platform: 'web', last_execution_status: 'success' }),
      createItem({ id: 'uc-2', name: 'Mobile Checkout', test_platform: 'mobile', last_execution_status: 'failed' }),
    ];

    render(<UsecasesTable items={items} />);

    expect(screen.getByText('Login Test')).toBeInTheDocument();
    expect(screen.getByText('Mobile Checkout')).toBeInTheDocument();
    expect(screen.getByText('Web')).toBeInTheDocument();
    expect(screen.getByText('Mobile')).toBeInTheDocument();
    expect(screen.getByText('success')).toBeInTheDocument();
    expect(screen.getByText('failed')).toBeInTheDocument();
  });

  it('filters items by search text', async () => {
    const items = [
      createItem({ id: 'uc-1', name: 'Login Test' }),
      createItem({ id: 'uc-2', name: 'Checkout Flow' }),
    ];

    render(<UsecasesTable items={items} showFilter={true} />);

    expect(screen.getByText('Login Test')).toBeInTheDocument();
    expect(screen.getByText('Checkout Flow')).toBeInTheDocument();

    const filterInput = screen.getByPlaceholderText('Search use cases by name, description, tags, or status');
    await userEvent.type(filterInput, 'Login');

    await waitFor(() => {
      expect(screen.getByText('Login Test')).toBeInTheDocument();
      expect(screen.queryByText('Checkout Flow')).not.toBeInTheDocument();
    });
  });

  it('shows "Never run" for usecases without last_execution_status', () => {
    const items = [
      createItem({ id: 'uc-1', name: 'New Test', last_execution_status: undefined }),
    ];

    render(<UsecasesTable items={items} />);

    expect(screen.getByText('Never run')).toBeInTheDocument();
  });

  it('calls onSelectionChange when items are selected', async () => {
    const onSelectionChange = vi.fn();
    const items = [
      createItem({ id: 'uc-1', name: 'Login Test' }),
      createItem({ id: 'uc-2', name: 'Checkout Flow' }),
    ];

    render(
      <UsecasesTable
        items={items}
        selectedItems={[]}
        onSelectionChange={onSelectionChange}
        selectionType="multi"
      />
    );

    // Cloudscape Table renders checkboxes for multi-select
    const checkboxes = screen.getAllByRole('checkbox');
    // First checkbox is "select all", individual items follow
    await userEvent.click(checkboxes[1]);

    expect(onSelectionChange).toHaveBeenCalled();
  });

  it('respects showPlatform=false by hiding platform column', () => {
    const items = [
      createItem({ id: 'uc-1', name: 'Test', test_platform: 'mobile' }),
    ];

    render(<UsecasesTable items={items} showPlatform={false} />);

    expect(screen.queryByText('Mobile')).not.toBeInTheDocument();
    expect(screen.queryByText('Web')).not.toBeInTheDocument();
    // The Platform column header should not appear
    expect(screen.queryByText('Platform')).not.toBeInTheDocument();
  });

  it('shows empty state when no items', () => {
    render(<UsecasesTable items={[]} />);

    expect(screen.getByText('No use cases found')).toBeInTheDocument();
  });
});
