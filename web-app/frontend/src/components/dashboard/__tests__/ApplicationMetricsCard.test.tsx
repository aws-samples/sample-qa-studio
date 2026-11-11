/**
 * The optional `cost` prop of the overview card: omitted → no cost column
 * (ApplicationDetailView renders the full CostCard instead), `null` → "—"
 * with the "No cost data yet" tooltip, a summary → 30-day figure with trend.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ApplicationMetricsCard } from '../ApplicationMetricsCard';
import { DashboardOverviewItem } from '../../../types/application';
import { CostSummary } from '../../../utils/api';

const app: DashboardOverviewItem = {
  id: 'app-1', name: 'Shop', base_url: 'https://shop.test', description: '', team: 'A',
  owner_team_id: 'team-a', environments: [], created_at: '', updated_at: '',
  last_execution_id: '', last_execution_status: 'failed', last_execution_at: '', usecase_count: 2,
  pass_rate: 80, total_executions: 10, failure_count: 2,
};

const summary: CostSummary = {
  as_of: '2026-11-04',
  window_1d: 1.42, window_1d_trend: 'up', window_1d_change_pct: 29.1, window_1d_list: 1.5,
  window_7d: 9.8, window_7d_trend: 'down', window_7d_change_pct: -10.1, window_7d_list: 10.2,
  window_30d: 42.1, window_30d_trend: 'up', window_30d_change_pct: 12, window_30d_list: 44.0,
  by_source_30d: { nova_act: 42.1 },
  days_available: 61,
  estimated_days: 1,
  updated_at: '2026-11-05T06:02:11Z',
};

describe('ApplicationMetricsCard cost column', () => {
  it('renders no cost column when the prop is omitted (backward compatible)', () => {
    render(<ApplicationMetricsCard app={app} />);
    expect(screen.getByText('Pass rate')).toBeInTheDocument();
    expect(screen.getByText('Executions')).toBeInTheDocument();
    expect(screen.getByText('Failures')).toBeInTheDocument();
    expect(screen.queryByText('Cost (30d)')).not.toBeInTheDocument();
    expect(screen.queryByTitle('No cost data yet')).not.toBeInTheDocument();
  });

  it('shows "—" with the "No cost data yet" tooltip when cost is null', () => {
    render(<ApplicationMetricsCard app={app} cost={null} />);
    expect(screen.getByText('Cost (30d)')).toBeInTheDocument();
    const placeholder = screen.getByTitle('No cost data yet');
    expect(placeholder).toHaveTextContent('—');
  });

  it('shows the 30-day amount with its trend when a summary is given', () => {
    render(<ApplicationMetricsCard app={app} cost={summary} />);
    expect(screen.getByText('Cost (30d)')).toBeInTheDocument();
    expect(screen.getByText('$42.10')).toBeInTheDocument();
    expect(screen.getByText('+12%')).toBeInTheDocument();
    expect(screen.getByLabelText('Cost rising')).toBeInTheDocument();
    expect(screen.queryByTitle('No cost data yet')).not.toBeInTheDocument();
    // The 30-day figure only; list price and the other windows stay on the detail pages.
    expect(screen.queryByText(/at list price/)).not.toBeInTheDocument();
    expect(screen.queryByText('$1.42')).not.toBeInTheDocument();
  });

  it('explains the window on hover', () => {
    render(<ApplicationMetricsCard app={app} cost={summary} />);
    expect(screen.getByText('Cost (30d)').closest('[title]')).toHaveAttribute(
      'title',
      'Allocated bill over the last 30 days, compared with the 30 days before',
    );
  });

  it('shows "not enough data" when the 30-day trend is null', () => {
    render(<ApplicationMetricsCard app={app} cost={{ ...summary, window_30d_trend: null, window_30d_change_pct: null }} />);
    expect(screen.getByText('$42.10')).toBeInTheDocument();
    expect(screen.getByText('not enough data')).toBeInTheDocument();
  });
});
