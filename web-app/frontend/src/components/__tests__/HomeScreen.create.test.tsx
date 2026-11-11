import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import HomeScreen from '../HomeScreen';

vi.mock('../../utils/api', () => ({
  api: { get: vi.fn().mockResolvedValue({ usecases: [] }), post: vi.fn(), delete: vi.fn() },
}));
vi.mock('../common/DeleteConfirmModal', () => ({ default: () => null }));

function Location() {
  const { pathname, search } = useLocation();
  return <div data-testid="location">{pathname + search}</div>;
}

describe('HomeScreen "Create Use Case"', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('opens the unified wizard', async () => {
    render(
      <MemoryRouter initialEntries={['/usecases']}>
        <Routes>
          <Route path="/usecases" element={<HomeScreen />} />
          <Route path="/create/new" element={<Location />} />
        </Routes>
      </MemoryRouter>,
    );

    await userEvent.click(await screen.findByRole('button', { name: 'Create Use Case' }));

    expect((await screen.findByTestId('location')).textContent).toBe('/create/new');
  });
});
