import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { TestSuitesTable } from '../TestSuitesTable';
import { TestSuite } from '../../../utils/api';

describe('TestSuitesTable', () => {
  const createSuite = (overrides: Partial<TestSuite> = {}): TestSuite => ({
    id: 'suite-1',
    name: 'Smoke Tests',
    description: 'Core smoke test suite',
    scope: 'smoke',
    tags: ['regression', 'p0'],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-10T00:00:00Z',
    created_by: 'user@example.com',
    total_usecases: 5,
    last_execution_status: 'completed',
    last_execution_time: '2026-01-15T10:00:00Z',
    schedule_enabled: false,
    ...overrides,
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders items with name, tags, and status', () => {
    const items = [
      createSuite({ id: 'suite-1', name: 'Smoke Tests', tags: ['regression'], last_execution_status: 'completed' }),
      createSuite({ id: 'suite-2', name: 'E2E Tests', tags: ['nightly'], last_execution_status: 'failed' }),
    ];

    render(<TestSuitesTable items={items} />);

    expect(screen.getByText('Smoke Tests')).toBeInTheDocument();
    expect(screen.getByText('E2E Tests')).toBeInTheDocument();
    expect(screen.getByText('regression')).toBeInTheDocument();
    expect(screen.getByText('nightly')).toBeInTheDocument();
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
  });

  it('filters items by search text', async () => {
    const items = [
      createSuite({ id: 'suite-1', name: 'Smoke Tests' }),
      createSuite({ id: 'suite-2', name: 'E2E Checkout' }),
    ];

    render(<TestSuitesTable items={items} showFilter={true} />);

    expect(screen.getByText('Smoke Tests')).toBeInTheDocument();
    expect(screen.getByText('E2E Checkout')).toBeInTheDocument();

    const filterInput = screen.getByPlaceholderText('Search by name, description, or tags');
    await userEvent.type(filterInput, 'Smoke');

    await waitFor(() => {
      expect(screen.getByText('Smoke Tests')).toBeInTheDocument();
      expect(screen.queryByText('E2E Checkout')).not.toBeInTheDocument();
    });
  });

  it('shows correct status indicators (completed=success, failed=error, never run=stopped)', () => {
    const items = [
      createSuite({ id: 'suite-1', name: 'Completed Suite', last_execution_status: 'completed' }),
      createSuite({ id: 'suite-2', name: 'Failed Suite', last_execution_status: 'failed' }),
      createSuite({ id: 'suite-3', name: 'Never Run Suite', last_execution_status: undefined }),
    ];

    render(<TestSuitesTable items={items} />);

    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
    expect(screen.getByText('Never run')).toBeInTheDocument();
  });

  it('respects showTags=false by hiding tags column', () => {
    const items = [
      createSuite({ id: 'suite-1', name: 'Test Suite', tags: ['important', 'p0'] }),
    ];

    render(<TestSuitesTable items={items} showTags={false} />);

    expect(screen.getByText('Test Suite')).toBeInTheDocument();
    // Tags column header should not be rendered
    expect(screen.queryByText('Tags')).not.toBeInTheDocument();
    // Tag values should not appear
    expect(screen.queryByText('important')).not.toBeInTheDocument();
    expect(screen.queryByText('p0')).not.toBeInTheDocument();
  });

  it('shows empty state when no items', () => {
    render(<TestSuitesTable items={[]} />);

    expect(screen.getByText('No test suites found')).toBeInTheDocument();
  });
});
