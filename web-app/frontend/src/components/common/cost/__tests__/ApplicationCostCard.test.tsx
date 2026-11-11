/**
 * ApplicationCostCard: `costsApi.application(id)` → CostCard with the
 * use-case table (name link, 1d / 7d / 30d, 30d trend). Hidden on 403/404,
 * error Alert on other failures, no write controls.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import { CostSummary, LedgerRow } from '../../../../utils/api';

const costsApplication = vi.fn();
vi.mock('../../../../utils/api', async () => {
  const actual = await vi.importActual<typeof import('../../../../utils/api')>('../../../../utils/api');
  return {
    ...actual,
    costsApi: { ...actual.costsApi, application: (...a: unknown[]) => costsApplication(...a) },
  };
});

import ApplicationCostCard from '../ApplicationCostCard';

const summary: CostSummary = {
  as_of: '2026-11-04',
  window_1d: 1.42, window_1d_trend: 'up', window_1d_change_pct: 29.1, window_1d_list: 1.5,
  window_7d: 9.8, window_7d_trend: 'down', window_7d_change_pct: -10.1, window_7d_list: 10.2,
  window_30d: 42.1, window_30d_trend: null, window_30d_change_pct: null, window_30d_list: 44.0,
  by_source_30d: { nova_act: 42.1 },
  days_available: 31,
  estimated_days: 1,
  updated_at: '2026-11-05T06:02:11Z',
};

const days: LedgerRow[] = [
  { date: '2026-11-04', estimated: true, cost: [{ service: 'nova_act', cost: 1.42, list_cost: 1.5, usage_seconds: 1076 }], collected_at: '2026-11-05T06:02:11Z' },
];

const checkoutSummary: CostSummary = {
  ...summary,
  window_1d: 0.5, window_1d_trend: 'flat', window_1d_change_pct: 1.0, window_1d_list: 0.55,
  window_7d: 3.2, window_7d_trend: 'up', window_7d_change_pct: 12.0, window_7d_list: 3.4,
  window_30d: 30.0, window_30d_trend: 'up', window_30d_change_pct: 25.0, window_30d_list: 31.0,
};

const response = {
  summary,
  days,
  usecases: [
    { usecase_id: 'uc-1', name: 'Checkout', summary: checkoutSummary },
    { usecase_id: 'uc-2', name: 'Login', summary: null },
  ],
};

function httpError(status: number, message = `HTTP ${status}`) {
  const err = new Error(message);
  (err as Error & { status: number }).status = status;
  return err;
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderCard() {
  return render(
    <MemoryRouter initialEntries={['/applications/app-1']}>
      <Routes>
        <Route path="/applications/:id" element={<ApplicationCostCard applicationId="app-1" />} />
        <Route path="*" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  costsApplication.mockReset();
});
afterEach(() => {
  cleanup();
});

describe('ApplicationCostCard', () => {
  it('requests the application costs once and renders the card with the windows', async () => {
    costsApplication.mockResolvedValue(response);
    renderCard();
    expect(await screen.findByRole('heading', { name: 'Cost' })).toBeInTheDocument();
    expect(screen.getByText('$42.10')).toBeInTheDocument();
    expect(screen.getByText('Source: Nova Act · Cost Explorer as of 2026-11-04 (estimated)')).toBeInTheDocument();
    expect(costsApplication).toHaveBeenCalledTimes(1);
    expect(costsApplication).toHaveBeenCalledWith('app-1');
  });

  it('lists the use cases with 1d / 7d / 30d cost and the 30d trend, as delivered', async () => {
    costsApplication.mockResolvedValue(response);
    renderCard();
    const table = await screen.findByRole('table');
    const rows = within(table).getAllByRole('row');
    // header + 2 use cases, in API order
    expect(rows).toHaveLength(3);
    expect(within(rows[1]).getByText('Checkout')).toBeInTheDocument();
    expect(within(rows[1]).getByText('$0.50')).toBeInTheDocument();
    expect(within(rows[1]).getByText('$3.20')).toBeInTheDocument();
    expect(within(rows[1]).getByText('$30.00')).toBeInTheDocument();
    expect(within(rows[1]).getByText('+25%')).toBeInTheDocument();
    expect(within(rows[2]).getByText('Login')).toBeInTheDocument();

    const headers = within(table).getAllByRole('columnheader').map((h) => h.textContent);
    expect(headers).toEqual(['Use case', 'Last day', 'Last 7 days', 'Last 30 days']);
    // No sortingField: headers must not be buttons (read-only assertions elsewhere).
    expect(within(table).queryAllByRole('button')).toHaveLength(0);
  });

  it('shows "No data" for a use case without a summary', async () => {
    costsApplication.mockResolvedValue(response);
    renderCard();
    const table = await screen.findByRole('table');
    const loginRow = within(table).getAllByRole('row')[2];
    expect(within(loginRow).getAllByText('No data')).toHaveLength(3);
  });

  it('links each use case to its detail page', async () => {
    costsApplication.mockResolvedValue(response);
    renderCard();
    await userEvent.click(await screen.findByRole('link', { name: 'Checkout' }));
    expect((await screen.findByTestId('location')).textContent).toBe('/usecase/uc-1');
  });

  it('renders the empty table state when the application has no use cases', async () => {
    costsApplication.mockResolvedValue({ ...response, usecases: [] });
    renderCard();
    expect(await screen.findByText('No use cases with cost data')).toBeInTheDocument();
  });

  it('shows the empty card state when the collector has not run yet', async () => {
    costsApplication.mockResolvedValue({ summary: null, days: [], usecases: [] });
    renderCard();
    expect(await screen.findByText('No cost data yet. Costs are collected once per day.')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it.each([403, 404])('renders nothing on %s', async (status) => {
    costsApplication.mockRejectedValue(httpError(status));
    const { container } = renderCard();
    await vi.waitFor(() => expect(costsApplication).toHaveBeenCalled());
    await vi.waitFor(() => expect(screen.queryByRole('heading', { name: 'Cost' })).not.toBeInTheDocument());
    expect(container.querySelector('[data-testid="location"]')).toBeNull();
    expect(container.textContent).toBe('');
  });

  it('shows an error Alert inside the card on other failures', async () => {
    costsApplication.mockRejectedValue(httpError(500, 'Internal Server Error'));
    renderCard();
    expect(await screen.findByText('Internal Server Error')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Cost' })).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('shows the loading state before the response arrives', () => {
    costsApplication.mockReturnValue(new Promise(() => undefined));
    renderCard();
    expect(screen.getByRole('heading', { name: 'Cost' })).toBeInTheDocument();
    expect(screen.queryByText(/No cost data yet/)).not.toBeInTheDocument();
    expect(screen.queryByText('Last 30 days')).not.toBeInTheDocument();
  });
});
