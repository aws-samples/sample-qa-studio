import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { CostTrend, formatUsd } from '../CostTrend';

/** Cloudscape `Box color="…"` renders a scoped class containing `color-<token>`. */
function hasColorClass(el: HTMLElement | null, token: string): boolean {
  return el?.closest(`[class*="color-${token}"]`) !== null;
}

describe('formatUsd', () => {
  it('formats USD with two decimals in en-US', () => {
    expect(formatUsd(1.42)).toBe('$1.42');
    expect(formatUsd(0)).toBe('$0.00');
    expect(formatUsd(1234.5)).toBe('$1,234.50');
    expect(formatUsd(0.004)).toBe('$0.00');
  });
});

describe('CostTrend', () => {
  it('shows the billed amount with two decimals', () => {
    render(<CostTrend amount={42.1} trend="flat" changePct={1.2} />);
    expect(screen.getByText('$42.10')).toBeInTheDocument();
  });

  it('shows the list-price figure as secondary text when given', () => {
    render(<CostTrend amount={0} listAmount={3.8} trend="flat" changePct={0} />);
    expect(screen.getByText('$0.00')).toBeInTheDocument();
    expect(screen.getByText('$3.80 at list price')).toBeInTheDocument();
  });

  it('omits the list-price line when listAmount is not given', () => {
    render(<CostTrend amount={1} trend="flat" changePct={0} />);
    expect(screen.queryByText(/at list price/)).not.toBeInTheDocument();
  });

  it('up: arrow up, signed percentage, warning colour', () => {
    render(<CostTrend amount={1.42} trend="up" changePct={29.1} />);
    const pct = screen.getByText('+29.1%');
    expect(hasColorClass(pct, 'text-status-warning')).toBe(true);
    expect(screen.getByRole('img', { name: 'Cost rising' })).toBeInTheDocument();
  });

  it('down: arrow down, negative percentage, success colour', () => {
    render(<CostTrend amount={1.42} trend="down" changePct={-8} />);
    const pct = screen.getByText('-8%');
    expect(hasColorClass(pct, 'text-status-success')).toBe(true);
    expect(screen.getByRole('img', { name: 'Cost falling' })).toBeInTheDocument();
  });

  it('flat: inherits the colour and shows the percentage inside the dead band', () => {
    render(<CostTrend amount={1.42} trend="flat" changePct={2} />);
    const pct = screen.getByText('+2%');
    expect(hasColorClass(pct, 'text-status-warning')).toBe(false);
    expect(hasColorClass(pct, 'text-status-success')).toBe(false);
    expect(screen.getByRole('img', { name: 'Cost unchanged' })).toBeInTheDocument();
  });

  it('trend null → "not enough data", no arrow, no percentage', () => {
    render(<CostTrend amount={1.42} trend={null} changePct={null} />);
    expect(screen.getByText('not enough data')).toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it('trend set but change_pct null (previous window was 0) → arrow only', () => {
    render(<CostTrend amount={1.42} trend="up" changePct={null} />);
    expect(screen.getByRole('img', { name: 'Cost rising' })).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    expect(screen.queryByText('not enough data')).not.toBeInTheDocument();
  });

  it('rounds the percentage to one decimal', () => {
    render(<CostTrend amount={1} trend="up" changePct={12.3456} />);
    expect(screen.getByText('+12.3%')).toBeInTheDocument();
  });

  it('inline variant renders amount and trend on one line without the large figure', () => {
    const { container } = render(<CostTrend amount={42.1} trend="up" changePct={12} variant="inline" />);
    expect(screen.getByText('$42.10')).toBeInTheDocument();
    expect(screen.getByText('+12%')).toBeInTheDocument();
    expect(container.querySelector('[class*="value-large-variant"]')).toBeNull();
  });

  it('large variant (default) uses the Cloudscape large value style', () => {
    const { container } = render(<CostTrend amount={42.1} trend="up" changePct={12} />);
    expect(container.querySelector('[class*="value-large-variant"]')).not.toBeNull();
  });
});
