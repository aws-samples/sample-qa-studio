/**
 * UsecaseCostCard: `costsApi.usecase(id)` → compact CostCard (windows +
 * sparkline, no table). Hidden on 403/404, error Alert otherwise.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { CostSummary, LedgerRow } from '../../../../utils/api';

const costsUsecase = vi.fn();
vi.mock('../../../../utils/api', async () => {
  const actual = await vi.importActual<typeof import('../../../../utils/api')>('../../../../utils/api');
  return {
    ...actual,
    costsApi: { ...actual.costsApi, usecase: (...a: unknown[]) => costsUsecase(...a) },
  };
});

import UsecaseCostCard from '../UsecaseCostCard';

const summary: CostSummary = {
  as_of: '2026-11-04',
  window_1d: 1.42, window_1d_trend: 'up', window_1d_change_pct: 29.1, window_1d_list: 1.5,
  window_7d: 9.8, window_7d_trend: 'down', window_7d_change_pct: -10.1, window_7d_list: 10.2,
  window_30d: 42.1, window_30d_trend: null, window_30d_change_pct: null, window_30d_list: 44.0,
  by_source_30d: { nova_act: 42.1 },
  days_available: 31,
  estimated_days: 0,
  updated_at: '2026-11-05T06:02:11Z',
};

const days: LedgerRow[] = [
  { date: '2026-11-04', estimated: false, cost: [{ service: 'nova_act', cost: 1.42, list_cost: 1.5, usage_seconds: 1076 }], collected_at: '2026-11-05T06:02:11Z' },
];

function httpError(status: number, message = `HTTP ${status}`) {
  const err = new Error(message);
  (err as Error & { status: number }).status = status;
  return err;
}

beforeEach(() => {
  costsUsecase.mockReset();
});
afterEach(() => {
  cleanup();
});

describe('UsecaseCostCard', () => {
  it('requests the use case costs once and renders the three windows and the sparkline', async () => {
    costsUsecase.mockResolvedValue({ summary, days });
    render(<UsecaseCostCard usecaseId="uc-1" />);
    expect(await screen.findByRole('heading', { name: 'Cost' })).toBeInTheDocument();
    expect(screen.getByText('$1.42')).toBeInTheDocument();
    expect(screen.getByText('$9.80')).toBeInTheDocument();
    expect(screen.getByText('$42.10')).toBeInTheDocument();
    expect(screen.getByLabelText('Daily cost, last 30 days')).toBeInTheDocument();
    expect(screen.getByText('Source: Nova Act · Cost Explorer as of 2026-11-04')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(costsUsecase).toHaveBeenCalledTimes(1);
    expect(costsUsecase).toHaveBeenCalledWith('uc-1');
  });

  it('has no write controls', async () => {
    costsUsecase.mockResolvedValue({ summary, days });
    render(<UsecaseCostCard usecaseId="uc-1" />);
    await screen.findByText('$42.10');
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.queryAllByRole('textbox')).toHaveLength(0);
  });

  it('shows the empty state when the collector has not run yet', async () => {
    costsUsecase.mockResolvedValue({ summary: null, days: [] });
    render(<UsecaseCostCard usecaseId="uc-1" />);
    expect(await screen.findByText('No cost data yet. Costs are collected once per day.')).toBeInTheDocument();
  });

  it.each([403, 404])('renders nothing on %s', async (status) => {
    costsUsecase.mockRejectedValue(httpError(status));
    const { container } = render(<UsecaseCostCard usecaseId="uc-1" />);
    await vi.waitFor(() => expect(container.textContent).toBe(''));
    expect(screen.queryByRole('heading', { name: 'Cost' })).not.toBeInTheDocument();
  });

  it('shows an error Alert inside the card on other failures', async () => {
    costsUsecase.mockRejectedValue(httpError(500, 'Internal Server Error'));
    render(<UsecaseCostCard usecaseId="uc-1" />);
    expect(await screen.findByText('Internal Server Error')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Cost' })).toBeInTheDocument();
  });

  it('refetches when the use case id changes', async () => {
    costsUsecase.mockResolvedValue({ summary, days });
    const { rerender } = render(<UsecaseCostCard usecaseId="uc-1" />);
    await screen.findByText('$42.10');
    rerender(<UsecaseCostCard usecaseId="uc-2" />);
    await vi.waitFor(() => expect(costsUsecase).toHaveBeenCalledTimes(2));
    expect(costsUsecase).toHaveBeenLastCalledWith('uc-2');
  });
});
