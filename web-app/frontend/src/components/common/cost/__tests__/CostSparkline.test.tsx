import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { CostSparkline, buildCostSeries } from '../CostSparkline';
import { LedgerRow, ServiceCost } from '../../../../utils/api';

function row(date: string, costs: number[], estimated = false): LedgerRow {
  const entries: ServiceCost[] = costs.map((cost, i) => ({
    service: i === 0 ? 'nova_act' : 'compute',
    cost,
    list_cost: cost,
    usage_seconds: 60,
  }));
  return {
    date,
    estimated,
    cost: entries,
    collected_at: '2026-11-05T06:02:11Z',
  };
}

describe('buildCostSeries', () => {
  it('sums cost[].cost per row into one "Billed" bar series over the dates', () => {
    const series = buildCostSeries([row('2026-11-01', [0.9, 0.1]), row('2026-11-02', [1.42])]);
    expect(series).toHaveLength(1);
    expect(series[0].title).toBe('Billed');
    expect(series[0].type).toBe('bar');
    expect(series[0].data).toEqual([
      { x: '2026-11-01', y: 1 },
      { x: '2026-11-02', y: 1.42 },
    ]);
  });

  it('puts estimated days into a second, differently coloured series (zeros elsewhere, so bars stack)', () => {
    const series = buildCostSeries([row('2026-11-01', [1]), row('2026-11-02', [2], true)]);
    expect(series.map((s) => s.title)).toEqual(['Billed', 'Billed (estimated)']);
    expect(series[0].data).toEqual([{ x: '2026-11-01', y: 1 }, { x: '2026-11-02', y: 0 }]);
    expect(series[1].data).toEqual([{ x: '2026-11-01', y: 0 }, { x: '2026-11-02', y: 2 }]);
    expect(series[0].color).not.toBe(series[1].color);
  });

  it('a row without cost entries is a zero bar', () => {
    const series = buildCostSeries([row('2026-11-01', [])]);
    expect(series[0].data).toEqual([{ x: '2026-11-01', y: 0 }]);
  });

  it('returns no series for no days', () => {
    expect(buildCostSeries([])).toEqual([]);
  });
});

describe('CostSparkline', () => {
  it('renders an accessible bar chart over the given days', () => {
    render(<CostSparkline days={[row('2026-11-01', [1]), row('2026-11-02', [2])]} />);
    expect(screen.getByLabelText('Daily cost, last 30 days')).toBeInTheDocument();
  });

  it('accepts a custom aria label', () => {
    render(<CostSparkline days={[row('2026-11-01', [1])]} ariaLabel="Login daily cost" />);
    expect(screen.getByLabelText('Login daily cost')).toBeInTheDocument();
  });

  it('shows the empty state when there are no days', () => {
    render(<CostSparkline days={[]} />);
    expect(screen.getByText('No cost data')).toBeInTheDocument();
  });
});
