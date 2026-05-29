import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import Box from '@cloudscape-design/components/box';
import Button from '@cloudscape-design/components/button';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Spinner from '@cloudscape-design/components/spinner';
import Alert from '@cloudscape-design/components/alert';
import SegmentedControl from '@cloudscape-design/components/segmented-control';
import { ApplicationSelector } from './ApplicationSelector';
import { ApplicationMetricsCard } from './ApplicationMetricsCard';
import { DashboardOverviewItem } from '../../types/application';
import { api } from '../../utils/api';


const AUTO_REFRESH_MS = 60_000;

export default function DashboardOverview() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [items, setItems] = useState<DashboardOverviewItem[]>([]);
  const [window, setWindow] = useState<'7d' | '30d'>('7d');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadData = useCallback(async (isManual = false) => {
    if (isManual) setRefreshing(true); else setLoading(true);
    setError('');
    try {
      const data = await api.get(`dashboard/overview?window=${window}`);
      setItems(data);
      setLastUpdated(new Date());
      if (data.length === 1) {
        navigate(`/applications/${data[0].id}`, { replace: true });
        return;
      }
    } catch (e: any) {
      setError(e.message || 'Failed to load dashboard');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [window, navigate]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    intervalRef.current = setInterval(() => loadData(), AUTO_REFRESH_MS);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [loadData]);

  if (loading) {
    return <Box textAlign="center" padding="xxl"><Spinner size="large" /></Box>;
  }

  if (error) {
    return <Alert type="error" header="Error">{error}</Alert>;
  }

  if (items.length === 0) {
    return (
      <Box textAlign="center" padding="xxl">
        <SpaceBetween size="m">
          <Box variant="h2">No applications configured</Box>
          <Box variant="p">Create an application from the Applications settings page to get started.</Box>
        </SpaceBetween>
      </Box>
    );
  }

  return (
    <SpaceBetween size="l">
      <Header
        variant="h1"
        description={lastUpdated ? `Last updated: ${lastUpdated.toLocaleTimeString()}` : undefined}
        actions={
          <SpaceBetween direction="horizontal" size="m">
            <Box>
              <ApplicationSelector
                applications={items}
                selectedId=""
                onChange={(id) => navigate(`/applications/${id}`)}
              />
            </Box>
            <SegmentedControl
              selectedId={window}
              onChange={({ detail }) => setWindow(detail.selectedId as '7d' | '30d')}
              options={[
                { id: '7d', text: '7 days' },
                { id: '30d', text: '30 days' },
              ]}
            />
            <Button iconName="refresh" loading={refreshing} onClick={() => loadData(true)}>
              Reload
            </Button>
          </SpaceBetween>
        }
      >
        Dashboard
      </Header>

      {items.map(app => (
        <ApplicationMetricsCard
          key={app.id}
          app={app}
          onClick={() => navigate(`/applications/${app.id}`)}
        />
      ))}
    </SpaceBetween>
  );
}
