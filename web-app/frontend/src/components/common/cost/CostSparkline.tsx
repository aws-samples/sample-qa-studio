import React from 'react';
import BarChart, { BarChartProps } from '@cloudscape-design/components/bar-chart';
import { LedgerRow } from '../../../utils/api';
import { formatUsd } from './CostTrend';

const BILLED_COLOR = '#0972d3';
const ESTIMATED_COLOR = '#8bb8e8';

const DEFAULT_HEIGHT = 120;
const DEFAULT_ARIA_LABEL = 'Daily cost, last 30 days';

export type CostBarSeries = BarChartProps.BarDataSeries<string>;

function dayTotal(row: LedgerRow): number {
  return row.cost.reduce((sum, entry) => sum + entry.cost, 0);
}

/**
 * One stacked bar per day: final days in the "Billed" series, days Cost
 * Explorer still marks `estimated` in a lighter second series (each series is
 * 0 on the other's days). The second series exists only when needed.
 */
export function buildCostSeries(days: LedgerRow[]): CostBarSeries[] {
  if (days.length === 0) return [];
  const billed: CostBarSeries = {
    title: 'Billed',
    type: 'bar',
    color: BILLED_COLOR,
    valueFormatter: formatUsd,
    data: days.map((row) => ({ x: row.date, y: row.estimated ? 0 : dayTotal(row) })),
  };
  if (!days.some((row) => row.estimated)) return [billed];
  const estimated: CostBarSeries = {
    title: 'Billed (estimated)',
    type: 'bar',
    color: ESTIMATED_COLOR,
    valueFormatter: formatUsd,
    data: days.map((row) => ({ x: row.date, y: row.estimated ? dayTotal(row) : 0 })),
  };
  return [billed, estimated];
}

export interface CostSparklineProps {
  /** Ledger rows, oldest first (the API returns the last 30). */
  days: LedgerRow[];
  /** Chart area height in px (default 120). */
  height?: number;
  /** Default "Daily cost, last 30 days". */
  ariaLabel?: string;
}

/** 30-day daily cost as a compact Cloudscape bar chart; no filter, no legend. */
export function CostSparkline({ days, height = DEFAULT_HEIGHT, ariaLabel = DEFAULT_ARIA_LABEL }: CostSparklineProps) {
  const series = buildCostSeries(days);
  const maxTotal = Math.max(0.01, ...days.map(dayTotal));
  return (
    <BarChart
      series={series}
      height={height}
      hideFilter
      hideLegend
      stackedBars
      xScaleType="categorical"
      xDomain={days.map((row) => row.date)}
      yDomain={[0, maxTotal]}
      xTickFormatter={(date) => date.slice(5)}
      yTickFormatter={formatUsd}
      ariaLabel={ariaLabel}
      i18nStrings={{
        chartAriaRoleDescription: 'bar chart',
        detailPopoverDismissAriaLabel: 'Dismiss',
        legendAriaLabel: 'Legend',
        xAxisAriaRoleDescription: 'date',
        yAxisAriaRoleDescription: 'cost in USD',
      }}
      empty="No cost data"
    />
  );
}
