import React from 'react';
import Box from '@cloudscape-design/components/box';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import KeyValuePairs from '@cloudscape-design/components/key-value-pairs';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Spinner from '@cloudscape-design/components/spinner';
import { CostSummary, LedgerRow } from '../../../utils/api';
import { CostSparkline } from './CostSparkline';
import { CostTrend } from './CostTrend';

/** `by_source_30d` keys → footer label; unknown sources fall back to the raw key. */
const SOURCE_LABELS: Record<string, string> = {
  nova_act: 'Nova Act',
  compute: 'Compute',
};

const NO_COST_DATA_MESSAGE = 'No cost data yet. Costs are collected once per day.';

function sourceLabels(summary: CostSummary): string {
  const sources = Object.keys(summary.by_source_30d);
  if (sources.length === 0) return SOURCE_LABELS.nova_act;
  return sources.map((source) => SOURCE_LABELS[source] ?? source).join(', ');
}

function footerText(summary: CostSummary): string {
  const estimated = summary.estimated_days > 0 ? ' (estimated)' : '';
  return `Source: ${sourceLabels(summary)} · Cost Explorer as of ${summary.as_of}${estimated}`;
}

export interface CostCardProps {
  /** `null` until the collector has run → empty state. */
  summary: CostSummary | null;
  /** Last 30 ledger rows for the sparkline. */
  days: LedgerRow[];
  loading: boolean;
  /** Container heading, default "Cost". */
  title?: string;
  /** Rendered below the sparkline (e.g. the application's use-case table). */
  children?: React.ReactNode;
}

/**
 * Cost container for application and use-case pages: the 1 / 7 / 30-day
 * windows with trend, the 30-day sparkline, an optional slot and the
 * "Source … as of …" footer.
 */
export function CostCard({ summary, days, loading, title = 'Cost', children }: CostCardProps) {
  const header = <Header variant="h2">{title}</Header>;

  if (loading) {
    return (
      <Container header={header}>
        <Box textAlign="center" padding="xxl"><Spinner size="large" /></Box>
      </Container>
    );
  }

  if (summary === null) {
    return (
      <Container header={header}>
        <Box textAlign="center" color="text-body-secondary" padding="l">{NO_COST_DATA_MESSAGE}</Box>
      </Container>
    );
  }

  return (
    <Container header={header} footer={<Box color="text-body-secondary" fontSize="body-s">{footerText(summary)}</Box>}>
      <SpaceBetween size="l">
        <KeyValuePairs
          columns={3}
          items={[
            {
              label: 'Last day',
              value: <CostTrend amount={summary.window_1d} listAmount={summary.window_1d_list} trend={summary.window_1d_trend} changePct={summary.window_1d_change_pct} />,
            },
            {
              label: 'Last 7 days',
              value: <CostTrend amount={summary.window_7d} listAmount={summary.window_7d_list} trend={summary.window_7d_trend} changePct={summary.window_7d_change_pct} />,
            },
            {
              label: 'Last 30 days',
              value: <CostTrend amount={summary.window_30d} listAmount={summary.window_30d_list} trend={summary.window_30d_trend} changePct={summary.window_30d_change_pct} />,
            },
          ]}
        />
        <CostSparkline days={days} />
        {children}
      </SpaceBetween>
    </Container>
  );
}
