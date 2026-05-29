import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import Box from '@cloudscape-design/components/box';
import Button from '@cloudscape-design/components/button';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Spinner from '@cloudscape-design/components/spinner';
import Alert from '@cloudscape-design/components/alert';
import SegmentedControl from '@cloudscape-design/components/segmented-control';
import Grid from '@cloudscape-design/components/grid';
import Table from '@cloudscape-design/components/table';
import Link from '@cloudscape-design/components/link';
import MixedLineBarChart from '@cloudscape-design/components/mixed-line-bar-chart';
import { ApplicationMetrics, ApplicationFailure, FlakyUsecase } from '../../types/application';
import { api } from '../../utils/api';

const AUTO_REFRESH_MS = 60_000;

interface MetricsTabProps {
  applicationId: string;
}

export function MetricsTab({ applicationId }: MetricsTabProps) {
  const navigate = useNavigate();
  const [metrics, setMetrics] = useState<ApplicationMetrics | null>(null);
  const [failures, setFailures] = useState<ApplicationFailure[]>([]);
  const [flaky, setFlaky] = useState<FlakyUsecase[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [window, setWindow] = useState<'7d' | '30d'>('7d');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadMetrics = useCallback(async (isManual = false) => {
    if (!applicationId) return;
    if (isManual) setRefreshing(true); else if (!metrics) setLoading(true);
    setError('');
    try {
      const [metricsData, failuresData, flakyData] = await Promise.all([
        api.get(`applications/${applicationId}/metrics?window=${window}`),
        api.get(`applications/${applicationId}/failures?limit=10`),
        api.get(`applications/${applicationId}/flaky`),
      ]);
      setMetrics(metricsData);
      setFailures(failuresData);
      setFlaky(flakyData);
      setLastUpdated(new Date());
    } catch (e: any) {
      setError(e.message || 'Failed to load metrics');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [applicationId, window]);

  useEffect(() => {
    loadMetrics();
  }, [loadMetrics]);

  useEffect(() => {
    intervalRef.current = setInterval(() => loadMetrics(), AUTO_REFRESH_MS);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [loadMetrics]);

  if (loading && !metrics) {
    return <Box textAlign="center" padding="xxl"><Spinner size="large" /></Box>;
  }

  if (error) {
    return <Alert type="error" header="Error">{error}</Alert>;
  }

  const totals = metrics?.totals;
  const series = metrics?.series;
  const velocity = totals && series && series.dates.length > 0 ? (totals.total_executions / series.dates.length).toFixed(1) : '0';
  const avgDuration = totals ? `${Math.round(totals.avg_duration_ms / 1000)}s` : '0s';

  return (
    <SpaceBetween size="l">
      <SpaceBetween direction="horizontal" size="m">
        <SegmentedControl
          selectedId={window}
          onChange={({ detail }) => setWindow(detail.selectedId as '7d' | '30d')}
          options={[
            { id: '7d', text: '7 days' },
            { id: '30d', text: '30 days' },
          ]}
        />
        <Button iconName="refresh" loading={refreshing} onClick={() => loadMetrics(true)}>
          Reload
        </Button>
        {lastUpdated && (
          <Box variant="small" color="text-body-secondary">
            Last updated: {lastUpdated.toLocaleTimeString()}
          </Box>
        )}
      </SpaceBetween>

      <Container>
        <SpaceBetween direction="horizontal" size="xl">
          <div>
            <Box variant="awsui-key-label">Pass rate</Box>
            <Box variant="awsui-value-large">{totals?.pass_rate || 0}%</Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Executions</Box>
            <Box variant="awsui-value-large">{totals?.total_executions || 0}</Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Failures</Box>
            <Box variant="awsui-value-large" color="text-status-error">
              {totals ? totals.total_executions - Math.round(totals.total_executions * totals.pass_rate / 100) : 0}
            </Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Velocity</Box>
            <Box variant="awsui-value-large">{velocity}/day</Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Avg Duration</Box>
            <Box variant="awsui-value-large">{avgDuration}</Box>
          </div>
          <div>
            <Box variant="awsui-key-label">Health Score</Box>
            <Box variant="awsui-value-large">{metrics?.health_score || 0}</Box>
          </div>
        </SpaceBetween>
      </Container>

      {series && series.dates.length > 0 && (
        <Container header={<Header variant="h2">Success vs Failed (daily)</Header>}>
          <MixedLineBarChart
            height={250}
            series={[
              {
                title: 'Total Executions',
                type: 'bar',
                data: series.dates.map((d, i) => ({ x: new Date(d), y: series.executions[i] || 0 })),
                color: '#687078',
              },
              {
                title: 'Successes',
                type: 'line',
                data: series.dates.map((d, i) => ({ x: new Date(d), y: series.successes[i] || 0 })),
                color: '#1d8102',
              },
              {
                title: 'Failures',
                type: 'line',
                data: series.dates.map((d, i) => ({ x: new Date(d), y: series.failures[i] || 0 })),
                color: '#d13212',
              },
            ]}
            xDomain={[new Date(series.dates[0]), new Date(series.dates[series.dates.length - 1])]}
            yDomain={[0, Math.max(...series.executions, 1)]}
            xScaleType="time"
            xTitle="Date"
            yTitle="Count"
            i18nStrings={{}}
            empty="No data for this period"
          />
        </Container>
      )}

      <Grid gridDefinition={[{ colspan: 6 }, { colspan: 6 }]}>
        <Container header={<Header variant="h2">Failure Hotspots</Header>}>
          <Table
            items={(() => {
              const grouped: Record<string, { usecase_id: string; usecase_name: string; error_message: string; count: number }> = {};
              for (const f of failures) {
                const key = `${f.usecase_id}::${f.error_message || ''}`;
                if (!grouped[key]) {
                  grouped[key] = { usecase_id: f.usecase_id, usecase_name: f.usecase_name, error_message: f.error_message, count: 0 };
                }
                grouped[key].count++;
              }
              return Object.values(grouped).sort((a, b) => b.count - a.count);
            })()}
            columnDefinitions={[
              {
                id: 'usecase_name',
                header: 'Usecase',
                cell: (item) => (
                  <Link onFollow={() => navigate(`/usecase/${item.usecase_id}`)}>
                    {item.usecase_name || item.usecase_id}
                  </Link>
                ),
              },
              {
                id: 'error_message',
                header: 'Error',
                cell: (item) => item.error_message || '-',
              },
              {
                id: 'count',
                header: 'Count',
                cell: (item) => item.count,
              },
            ]}
            empty="No failures recorded"
            variant="embedded"
          />
        </Container>

        <Container header={<Header variant="h2">Flaky Usecases</Header>}>
          <Table
            items={flaky}
            columnDefinitions={[
              {
                id: 'usecase_name',
                header: 'Usecase',
                cell: (item) => item.usecase_name || item.usecase_id,
              },
              {
                id: 'flip_count_7d',
                header: 'Flips (7d)',
                cell: (item) => item.flip_count_7d,
              },
              {
                id: 'last_flip_at',
                header: 'Last Flip',
                cell: (item) => item.last_flip_at ? new Date(item.last_flip_at).toLocaleDateString() : '-',
              },
            ]}
            empty="No flaky usecases detected"
            variant="embedded"
          />
        </Container>
      </Grid>
    </SpaceBetween>
  );
}
