/**
 * Unified applications page: health metrics (formerly the dashboard overview)
 * and application management (formerly the applications settings table) in one
 * card grid. Reached from `/applications`; `/` redirects here.
 *
 * Refresh is silent by design: only the initial load shows a spinner. Manual
 * reloads, window changes and the 60 s auto-refresh swap data in place, and a
 * failed refetch keeps the current data behind a dismissible alert.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Alert from '@cloudscape-design/components/alert';
import Box from '@cloudscape-design/components/box';
import Button from '@cloudscape-design/components/button';
import Grid from '@cloudscape-design/components/grid';
import Header from '@cloudscape-design/components/header';
import SegmentedControl from '@cloudscape-design/components/segmented-control';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Spinner from '@cloudscape-design/components/spinner';
import { ApplicationCard } from './ApplicationCard';
import { ApplicationSelector } from '../dashboard/ApplicationSelector';
import { CreateApplicationModal } from '../dashboard/CreateApplicationModal';
import DeleteConfirmModal, { DeleteNoun } from '../common/DeleteConfirmModal';
import { DashboardOverviewItem } from '../../types/application';
import { api, costsApi, CostSummary } from '../../utils/api';
import { usePermissions, canCreateApplication } from '../../auth';

const AUTO_REFRESH_MS = 60_000;

const APPLICATION_DELETE_NOUN: DeleteNoun = { singular: 'application', plural: 'applications', title: 'Application' };

/** Per-application cost summaries. Never rejects: a failure renders every cost cell as "—". */
async function loadCostMap(): Promise<Map<string, CostSummary | null>> {
  try {
    const response = await costsApi.dashboard();
    return new Map(response.applications.map((row) => [row.application_id, row.summary]));
  } catch (e) {
    console.error('Failed to load dashboard costs:', e);
    return new Map();
  }
}

/** Suite counts per application, derived client-side. `null` when the request fails → footer omits the link. */
async function loadSuiteCounts(): Promise<Map<string, number> | null> {
  try {
    const data = await api.get('test-suites');
    const suites = data.suites || data || [];
    const counts = new Map<string, number>();
    for (const suite of suites) {
      if (suite.application_id) {
        counts.set(suite.application_id, (counts.get(suite.application_id) || 0) + 1);
      }
    }
    return counts;
  } catch (e) {
    console.error('Failed to load test suites for the application cards:', e);
    return null;
  }
}

export default function ApplicationsPage() {
  const navigate = useNavigate();
  const { isAdmin, teams } = usePermissions();
  const canCreate = canCreateApplication(isAdmin, teams);
  const [items, setItems] = useState<DashboardOverviewItem[]>([]);
  const [costs, setCosts] = useState<Map<string, CostSummary | null>>(new Map());
  const [suiteCounts, setSuiteCounts] = useState<Map<string, number> | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshError, setRefreshError] = useState('');
  const [window, setWindow] = useState<'7d' | '30d'>('7d');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [createVisible, setCreateVisible] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DashboardOverviewItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const firstLoad = useRef(true);

  const loadData = useCallback(async () => {
    const isFirst = firstLoad.current;
    try {
      const [data, costMap, suites] = await Promise.all([
        api.get(`dashboard/overview?window=${window}`),
        loadCostMap(),
        loadSuiteCounts(),
      ]);
      setItems(data);
      setCosts(costMap);
      setSuiteCounts(suites);
      setLastUpdated(new Date());
      setRefreshError('');
    } catch (e: any) {
      if (isFirst) {
        setError(e.message || 'Failed to load applications');
      } else {
        // Silent refresh keeps the stale data behind a dismissible alert.
        setRefreshError(e.message || 'Failed to refresh applications');
      }
    } finally {
      firstLoad.current = false;
      if (isFirst) setInitialLoading(false);
    }
  }, [window]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    const interval = setInterval(() => loadData(), AUTO_REFRESH_MS);
    return () => clearInterval(interval);
  }, [loadData]);

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.delete(`applications/${deleteTarget.id}`);
      setDeleteTarget(null);
      await loadData();
    } catch (e: any) {
      setRefreshError(e.message || 'Failed to delete application');
    } finally {
      setDeleting(false);
    }
  }

  if (initialLoading) {
    return <Box textAlign="center" padding="xxl"><Spinner size="large" /></Box>;
  }

  if (error) {
    return <Alert type="error" header="Error">{error}</Alert>;
  }

  if (items.length === 0) {
    return (
      <SpaceBetween size="l">
        <Header
          variant="h1"
          actions={
            canCreate && (
              <Button variant="primary" onClick={() => setCreateVisible(true)}>
                Create application
              </Button>
            )
          }
        >
          Applications
        </Header>
        <Box textAlign="center" padding="xxl">
          <SpaceBetween size="m">
            <Box variant="h2">No applications yet</Box>
            {canCreate && (
              <div>
                <Button onClick={() => setCreateVisible(true)}>Create your first application</Button>
              </div>
            )}
          </SpaceBetween>
        </Box>
        <CreateApplicationModal
          visible={createVisible}
          onDismiss={() => setCreateVisible(false)}
          onSuccess={loadData}
        />
      </SpaceBetween>
    );
  }

  return (
    <SpaceBetween size="l">
      {refreshError && (
        <Alert type="error" dismissible onDismiss={() => setRefreshError('')}>{refreshError}</Alert>
      )}

      <Header
        variant="h1"
        description={
          lastUpdated
            ? `Last updated: ${lastUpdated.toLocaleTimeString()}`
            : 'Applications under test — health, cost and management in one place.'
        }
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
            <Button iconName="refresh" onClick={() => loadData()}>
              Reload
            </Button>
            {canCreate && (
              <Button variant="primary" onClick={() => setCreateVisible(true)}>
                Create application
              </Button>
            )}
          </SpaceBetween>
        }
      >
        Applications
      </Header>

      <Grid gridDefinition={items.map(() => ({ colspan: { default: 12, m: 6, xl: 4 } }))}>
        {items.map((app) => (
          <ApplicationCard
            key={app.id}
            app={app}
            cost={costs.get(app.id) ?? null}
            suiteCount={suiteCounts ? (suiteCounts.get(app.id) ?? 0) : null}
            onDelete={setDeleteTarget}
          />
        ))}
      </Grid>

      <CreateApplicationModal
        visible={createVisible}
        onDismiss={() => setCreateVisible(false)}
        onSuccess={loadData}
      />

      {/* Mounted only while open: a hidden Cloudscape Modal still renders its Delete button. */}
      {deleteTarget && (
        <DeleteConfirmModal
          visible
          count={1}
          noun={APPLICATION_DELETE_NOUN}
          consequences={`Usecases and test suites are not deleted; their association with ${deleteTarget.name} is removed.`}
          onConfirm={handleDelete}
          onDismiss={() => setDeleteTarget(null)}
          loading={deleting}
        />
      )}
    </SpaceBetween>
  );
}
