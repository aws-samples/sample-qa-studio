import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { CostCard } from '../CostCard';
import { CostSummary, LedgerRow } from '../../../../utils/api';

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
  { date: '2026-11-03', estimated: false, cost: [{ service: 'nova_act', cost: 1.1, list_cost: 1.2, usage_seconds: 800 }], collected_at: '2026-11-05T06:02:11Z' },
  { date: '2026-11-04', estimated: true, cost: [{ service: 'nova_act', cost: 1.42, list_cost: 1.5, usage_seconds: 1076 }], collected_at: '2026-11-05T06:02:11Z' },
];

describe('CostCard', () => {
  it('renders the three windows with billed amount, list price and trend', () => {
    render(<CostCard summary={summary} days={days} loading={false} />);

    expect(screen.getByText('Last day')).toBeInTheDocument();
    expect(screen.getByText('Last 7 days')).toBeInTheDocument();
    expect(screen.getByText('Last 30 days')).toBeInTheDocument();

    expect(screen.getByText('$1.42')).toBeInTheDocument();
    expect(screen.getByText('$9.80')).toBeInTheDocument();
    expect(screen.getByText('$42.10')).toBeInTheDocument();

    expect(screen.getByText('$1.50 at list price')).toBeInTheDocument();
    expect(screen.getByText('$10.20 at list price')).toBeInTheDocument();
    expect(screen.getByText('$44.00 at list price')).toBeInTheDocument();

    expect(screen.getByText('+29.1%')).toBeInTheDocument();
    expect(screen.getByText('-10.1%')).toBeInTheDocument();
    expect(screen.getByText('not enough data')).toBeInTheDocument();
  });

  it('renders the 30-day sparkline', () => {
    render(<CostCard summary={summary} days={days} loading={false} />);
    expect(screen.getByLabelText('Daily cost, last 30 days')).toBeInTheDocument();
  });

  it('footer names the sources and the Cost Explorer as-of date, marked estimated when estimated_days > 0', () => {
    render(<CostCard summary={summary} days={days} loading={false} />);
    expect(screen.getByText('Source: Nova Act · Cost Explorer as of 2026-11-04 (estimated)')).toBeInTheDocument();
  });

  it('footer drops "(estimated)" when no day in the window is estimated', () => {
    render(<CostCard summary={{ ...summary, estimated_days: 0 }} days={days} loading={false} />);
    expect(screen.getByText('Source: Nova Act · Cost Explorer as of 2026-11-04')).toBeInTheDocument();
  });

  it('footer lists every source in by_source_30d', () => {
    render(
      <CostCard summary={{ ...summary, by_source_30d: { nova_act: 39, compute: 3.1 } }} days={days} loading={false} />,
    );
    expect(screen.getByText('Source: Nova Act, Compute · Cost Explorer as of 2026-11-04 (estimated)')).toBeInTheDocument();
  });

  it('footer falls back to Nova Act when by_source_30d is empty', () => {
    render(<CostCard summary={{ ...summary, by_source_30d: {} }} days={days} loading={false} />);
    expect(screen.getByText(/^Source: Nova Act · /)).toBeInTheDocument();
  });

  it('empty state when summary is null', () => {
    render(<CostCard summary={null} days={[]} loading={false} />);
    expect(screen.getByText('No cost data yet. Costs are collected once per day.')).toBeInTheDocument();
    expect(screen.queryByText(/Cost Explorer as of/)).not.toBeInTheDocument();
    expect(screen.queryByText('Last 30 days')).not.toBeInTheDocument();
  });

  it('loading shows neither figures nor the empty state', () => {
    render(<CostCard summary={null} days={[]} loading />);
    expect(screen.queryByText(/No cost data yet/)).not.toBeInTheDocument();
    expect(screen.queryByText('Last 30 days')).not.toBeInTheDocument();
  });

  it('uses "Cost" as the default title and accepts another', () => {
    const { unmount } = render(<CostCard summary={summary} days={days} loading={false} />);
    expect(screen.getByRole('heading', { name: 'Cost' })).toBeInTheDocument();
    unmount();
    render(<CostCard summary={summary} days={days} loading={false} title="Application cost" />);
    expect(screen.getByRole('heading', { name: 'Application cost' })).toBeInTheDocument();
  });

  it('renders children below the windows (the use-case table slot)', () => {
    render(
      <CostCard summary={summary} days={days} loading={false}>
        <div data-testid="usecase-table">table</div>
      </CostCard>,
    );
    expect(screen.getByTestId('usecase-table')).toBeInTheDocument();
  });
});
