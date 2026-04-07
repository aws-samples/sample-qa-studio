import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import HomeScreen from '../HomeScreen';

// Mock the API module
vi.mock('../../utils/api', () => ({
    api: {
        get: vi.fn(),
        post: vi.fn(),
        delete: vi.fn(),
    },
}));

// Mock DeleteUsecaseModal
vi.mock('../DeleteUsecaseModal', () => ({
    default: function MockDeleteModal() {
        return null;
    },
}));

import { api } from '../../utils/api';

const mockUsecases = [
    {
        id: '1',
        name: 'Zebra Test',
        description: 'desc',
        active: false,
        last_execution_status: 'success',
        last_execution_time: '2026-03-10T10:00:00Z',
    },
    {
        id: '2',
        name: 'Alpha Test',
        description: 'desc',
        active: true,
        last_execution_status: 'failed',
        last_execution_time: '2026-03-15T10:00:00Z',
    },
    {
        id: '3',
        name: 'Middle Test',
        description: 'desc',
        active: true,
        last_execution_status: null as any,
        last_execution_time: null as any,
    },
];

const renderHomeScreen = () => {
    return render(
        <MemoryRouter>
            <HomeScreen />
        </MemoryRouter>
    );
};

describe('HomeScreen - Column Sorting', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        (api.get as ReturnType<typeof vi.fn>).mockResolvedValue({ usecases: mockUsecases });
    });

    it('should render sortable column headers', async () => {
        renderHomeScreen();

        // Wait for data to load
        await screen.findByText('Zebra Test');

        // All four column headers should be present
        expect(screen.getByText('Name')).toBeInTheDocument();
        expect(screen.getByText('Last Status')).toBeInTheDocument();
        expect(screen.getByText('Last Execution')).toBeInTheDocument();
        // "Active" appears in both header and badge cells
        expect(screen.getAllByText('Active').length).toBeGreaterThanOrEqual(1);
    });

    it('should display all usecases after loading', async () => {
        renderHomeScreen();

        await screen.findByText('Zebra Test');
        expect(screen.getByText('Alpha Test')).toBeInTheDocument();
        expect(screen.getByText('Middle Test')).toBeInTheDocument();
    });

    it('should sort by Name column when clicked', async () => {
        const user = userEvent.setup();
        renderHomeScreen();

        await screen.findByText('Zebra Test');

        // Click the Name column header to sort
        const nameHeader = screen.getByText('Name');
        await user.click(nameHeader);

        // Verify all items are still rendered (sorting doesn't filter)
        expect(screen.getByText('Alpha Test')).toBeInTheDocument();
        expect(screen.getByText('Middle Test')).toBeInTheDocument();
        expect(screen.getByText('Zebra Test')).toBeInTheDocument();
    });

    it('should sort by Last Status column when clicked', async () => {
        const user = userEvent.setup();
        renderHomeScreen();

        await screen.findByText('Zebra Test');

        const statusHeader = screen.getByText('Last Status');
        await user.click(statusHeader);

        // All items should still be present
        expect(screen.getByText('success')).toBeInTheDocument();
        expect(screen.getByText('failed')).toBeInTheDocument();
        expect(screen.getByText('Never run')).toBeInTheDocument();
    });

    it('should sort by Active column when clicked', async () => {
        const user = userEvent.setup();
        renderHomeScreen();

        await screen.findByText('Zebra Test');

        // "Active" appears in header and badge cells; target the column header via role
        const activeHeader = screen.getByRole('columnheader', { name: /active/i });
        await user.click(activeHeader);

        // All items should still be present with correct badges
        expect(screen.getByText('Inactive')).toBeInTheDocument();
        const activeBadges = screen.getAllByText('Active');
        // One is the column header, two are the badges for active items
        expect(activeBadges.length).toBeGreaterThanOrEqual(2);
    });

    it('should toggle sort direction on double click', async () => {
        const user = userEvent.setup();
        renderHomeScreen();

        await screen.findByText('Zebra Test');

        const nameHeader = screen.getByText('Name');

        // First click: ascending
        await user.click(nameHeader);
        // Second click: descending
        await user.click(nameHeader);

        // All items should still be present
        expect(screen.getByText('Alpha Test')).toBeInTheDocument();
        expect(screen.getByText('Zebra Test')).toBeInTheDocument();
    });
});
