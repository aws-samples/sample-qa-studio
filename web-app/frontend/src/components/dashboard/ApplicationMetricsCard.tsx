import React from 'react';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import Link from '@cloudscape-design/components/link';
import SpaceBetween from '@cloudscape-design/components/space-between';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Grid from '@cloudscape-design/components/grid';
import Box, { BoxProps } from '@cloudscape-design/components/box';
import LineChart from '@cloudscape-design/components/line-chart';
import { DashboardOverviewItem } from '../../types/application';
import { CostSummary } from '../../utils/api';
import { CostTrend } from '../common/cost/CostTrend';

const COST_WINDOW_HINT = 'Allocated bill over the last 30 days, compared with the 30 days before';
export const NO_COST_DATA_HINT = 'No cost data yet';

export function formatRelativeTime(isoString: string): string {
  if (!isoString) return 'Never';
  const diff = Date.now() - new Date(isoString).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function getPassRateColor(rate: number): BoxProps.Color {
  if (rate >= 90) return 'text-status-success';
  if (rate >= 70) return 'text-status-warning';
  return 'text-status-error';
}

export function getStatusType(status: string): 'success' | 'error' | 'warning' | 'info' | 'stopped' {
  if (status === 'success') return 'success';
  if (status === 'failed') return 'error';
  return 'info';
}

interface ApplicationMetricsCardProps {
  app: DashboardOverviewItem;
  onClick?: () => void;
  hideHeader?: boolean;
  /**
   * 30-day cost of the application (`/dashboard/costs` row). Omit to render
   * no cost column (the application detail page shows the full `CostCard`);
   * `null` = no summary yet → "—".
   */
  cost?: CostSummary | null;
}

/** Fourth large value of the card: the 30-day cost with its trend, or "—" when no summary exists. */
function CostValue({ cost }: { cost: CostSummary | null }) {
  if (cost === null) {
    return (
      <Box variant="awsui-value-large" color="text-body-secondary">
        <span title={NO_COST_DATA_HINT}>—</span>
      </Box>
    );
  }
  return <CostTrend amount={cost.window_30d} trend={cost.window_30d_trend} changePct={cost.window_30d_change_pct} />;
}

export function ApplicationMetricsCard({ app, onClick, hideHeader, cost }: ApplicationMetricsCardProps) {
  const header = hideHeader ? undefined : (
    <Header
      variant="h2"
      description={
        <StatusIndicator type={getStatusType(app.last_execution_status)}>
          Last run: {app.last_execution_status || 'never'} {formatRelativeTime(app.last_execution_at)}
        </StatusIndicator>
      }
    >
      {onClick ? (
        <Link fontSize="heading-m" onFollow={(e) => { e.preventDefault(); onClick(); }}>{app.name}</Link>
      ) : (
        app.name
      )}
    </Header>
  );

  return (
    <Container header={header} data-testid="application-metrics-card">
      <Grid gridDefinition={[{ colspan: 4 }, { colspan: 8 }]}>
        <SpaceBetween direction="horizontal" size="xl">
          <div>
            <Box variant="awsui-key-label">Pass rate</Box>
            <Box variant="awsui-value-large" color={getPassRateColor(app.pass_rate || 0)}>
              {app.pass_rate || 0}%
            </Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Executions</Box>
            <Box variant="awsui-value-large">{app.total_executions || 0}</Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Failures</Box>
            <Box variant="awsui-value-large" color="text-status-error">
              {app.failure_count || 0}
            </Box>
          </div>
          {cost !== undefined && (
            <div title={COST_WINDOW_HINT}>
              <Box variant="awsui-key-label">Cost (30d)</Box>
              <CostValue cost={cost} />
            </div>
          )}
        </SpaceBetween>
        <div>
          {app.series && app.series.dates.length > 0 && (
            <LineChart
              height={120}
              hideFilter
              hideLegend
              series={[
                {
                  title: 'Successes',
                  type: 'line',
                  data: app.series.dates.map((d, i) => ({ x: new Date(d), y: app.series!.successes[i] || 0 })),
                  color: '#1d8102',
                },
                {
                  title: 'Failures',
                  type: 'line',
                  data: app.series.dates.map((d, i) => ({ x: new Date(d), y: app.series!.failures[i] || 0 })),
                  color: '#d13212',
                },
              ]}
              xDomain={[new Date(app.series.dates[0]), new Date(app.series.dates[app.series.dates.length - 1])]}
              yDomain={[0, Math.max(...app.series.successes, ...app.series.failures, 1)]}
              xScaleType="time"
              i18nStrings={{}}
              empty="No data"
            />
          )}
        </div>
      </Grid>
    </Container>
  );
}
