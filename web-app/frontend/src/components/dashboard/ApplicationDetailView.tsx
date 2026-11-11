import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import Box from '@cloudscape-design/components/box';
import BreadcrumbGroup from '@cloudscape-design/components/breadcrumb-group';
import Button from '@cloudscape-design/components/button';
import Container from '@cloudscape-design/components/container';
import ButtonDropdown from '@cloudscape-design/components/button-dropdown';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Spinner from '@cloudscape-design/components/spinner';
import Alert from '@cloudscape-design/components/alert';
import Flashbar, { type FlashbarProps } from '@cloudscape-design/components/flashbar';
import Tabs from '@cloudscape-design/components/tabs';
import { ApplicationMetricsCard } from './ApplicationMetricsCard';
import { MetricsTab } from './MetricsTab';
import ApplicationCostCard from '../common/cost/ApplicationCostCard';
import DeleteConfirmModal from '../common/DeleteConfirmModal';
import { ReassignTeamModal } from './ReassignTeamModal';
import { UsecasesTable, UsecaseItem } from '../common/UsecasesTable';
import { TestSuitesTable } from '../common/TestSuitesTable';
import { DashboardOverviewItem } from '../../types/application';
import { api, TestSuite } from '../../utils/api';
import { useBatchExecute } from '../../hooks/useBatchExecute';
import {
  useBatchDelete,
  deleteInProgressFlash,
  deleteResultFlashes,
  USECASE_DELETE_NOUN,
  USECASE_DELETE_CONSEQUENCES,
} from '../../hooks/useBatchDelete';
import { usePermissions, canManageApplication } from '../../auth';
import { APPLICATION_CONFIG_PAGES, applicationConfigHref } from '../applications/applicationNav';


export default function ApplicationDetailView() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTabId, setActiveTabId] = useState(searchParams.get('tab') || 'usecases');

  useEffect(() => {
    const tabFromUrl = searchParams.get('tab');
    if (tabFromUrl && tabFromUrl !== activeTabId) {
      setActiveTabId(tabFromUrl);
    }
  }, [searchParams]);

  const handleTabChange = (tabId: string) => {
    setActiveTabId(tabId);
    setSearchParams({ tab: tabId });
  };

  const [app, setApp] = useState<DashboardOverviewItem | null>(null);
  const [usecases, setUsecases] = useState<UsecaseItem[]>([]);
  const [testSuites, setTestSuites] = useState<TestSuite[]>([]);
  const [selectedUsecases, setSelectedUsecases] = useState<UsecaseItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState('');
  const { executeBatch, executing } = useBatchExecute();
  const { deleteBatch, deleting } = useBatchDelete();
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  // Delete results live in a Flashbar, not in `error`: `error` replaces the whole page with an Alert.
  const [flashbarItems, setFlashbarItems] = useState<FlashbarProps.MessageDefinition[]>([]);
  const { isAdmin, teams } = usePermissions();
  const [reassignVisible, setReassignVisible] = useState(false);

  const loadData = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError('');
    try {
      const [appData, overviewData] = await Promise.all([
        api.get(`applications/${id}`),
        api.get(`dashboard/overview?window=7d`),
      ]);

      const overview = (overviewData as DashboardOverviewItem[]).find(a => a.id === id);
      setApp(overview || { ...appData, pass_rate: 0, total_executions: 0, failure_count: 0 });

      // Load associated usecases by filtering all usecases that have this application_id
      const allUsecases = await api.get('usecases');
      const associated = (allUsecases.usecases || []).filter(
        (uc: any) => uc.application_id === id
      );
      setUsecases(associated);

      // Load test suites associated with this application
      const allSuites = await api.get('test-suites');
      const associatedSuites = (allSuites.suites || allSuites || []).filter(
        (suite: any) => suite.application_id === id
      );
      setTestSuites(associatedSuites);
    } catch (e: any) {
      setError(e.message || 'Failed to load application');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function handleRemoveUsecases() {
    if (selectedUsecases.length === 0 || !id) return;
    setRemoving(true);
    try {
      await api.post(`applications/${id}/usecases`, {
        action: 'remove',
        usecase_ids: selectedUsecases.map(uc => uc.id),
      });
      setSelectedUsecases([]);
      await loadData();
    } catch (e: any) {
      setError(e.message || 'Failed to remove usecases');
    } finally {
      setRemoving(false);
    }
  }

  async function handleExecuteSelected() {
    if (selectedUsecases.length === 0) return;
    const results = await executeBatch(selectedUsecases);
    const failures = results.filter(r => !r.success);
    if (failures.length > 0) {
      setError(`Failed to start ${failures.length} execution(s): ${failures.map(f => f.usecaseName).join(', ')}`);
    }
    setSelectedUsecases([]);
  }

  async function handleDeleteSelected() {
    setShowDeleteModal(false);
    if (selectedUsecases.length === 0) return;
    setFlashbarItems([deleteInProgressFlash(selectedUsecases.length)]);
    const results = await deleteBatch(selectedUsecases);
    setFlashbarItems(deleteResultFlashes(results, () => setFlashbarItems([])));
    setSelectedUsecases([]);
    await loadData();
  }

  if (loading) {
    return <Box textAlign="center" padding="xxl"><Spinner size="large" /></Box>;
  }

  if (error) {
    return <Alert type="error" header="Error">{error}</Alert>;
  }

  if (!app) {
    return <Alert type="error">Application not found</Alert>;
  }

  return (
    <SpaceBetween size="l">
      <BreadcrumbGroup
        items={[
          { text: 'Applications', href: '/applications' },
          { text: app.name, href: `/applications/${id}` },
        ]}
        onFollow={(event) => { event.preventDefault(); navigate(event.detail.href); }}
      />

      {flashbarItems.length > 0 && <Flashbar items={flashbarItems} />}

      <Header
        variant="h1"
        actions={
          <SpaceBetween direction="horizontal" size="m">
            <ButtonDropdown
              data-testid="application-actions"
              onItemClick={({ detail }) => {
                if (detail.id === 'reassign') setReassignVisible(true);
                if (detail.id === 'edit') navigate(`/applications/${id}/edit`);
                const page = APPLICATION_CONFIG_PAGES.find((p) => p.slug === detail.id);
                if (page) navigate(applicationConfigHref(id!, page.slug));
              }}
              items={[
                ...(canManageApplication(isAdmin, teams, app.owner_team_id) ? [{ id: 'edit', text: 'Edit' }] : []),
                ...(isAdmin ? [{ id: 'reassign', text: 'Assign to team' }] : []),
                {
                  id: 'configuration',
                  text: 'Configuration',
                  items: APPLICATION_CONFIG_PAGES.map((p) => ({ id: p.slug, text: p.text })),
                },
              ]}
            >
              Actions
            </ButtonDropdown>
            <Button variant="primary" onClick={() => navigate(`/create/new?applicationId=${id}`)}>Create usecase</Button>
          </SpaceBetween>
        }
      >
        {app.name}
      </Header>

      {isAdmin && (
        <ReassignTeamModal
          visible={reassignVisible}
          onDismiss={() => setReassignVisible(false)}
          onSuccess={loadData}
          applicationId={id!}
          applicationName={app.name}
          currentTeamId={(app as any).owner_team_id}
        />
      )}

      <ApplicationMetricsCard app={app} hideHeader />

      {/* Mounted only while open: a hidden Cloudscape Modal still renders its Delete button. */}
      {showDeleteModal && (
        <DeleteConfirmModal
          visible
          count={selectedUsecases.length}
          noun={USECASE_DELETE_NOUN}
          consequences={USECASE_DELETE_CONSEQUENCES}
          onConfirm={handleDeleteSelected}
          onDismiss={() => setShowDeleteModal(false)}
          loading={deleting}
        />
      )}

      <Tabs
        activeTabId={activeTabId}
        onChange={({ detail }) => handleTabChange(detail.activeTabId)}
        tabs={[
          {
            id: 'usecases',
            label: `Usecases (${usecases.length})`,
            content: (
              <UsecasesTable
                items={usecases}
                selectedItems={selectedUsecases}
                onSelectionChange={setSelectedUsecases}
                showPlatform={true}
                header={
                  <Header
                    variant="h2"
                    actions={
                      <ButtonDropdown
                        data-testid="usecase-actions"
                        variant="primary"
                        loading={executing || removing || deleting}
                        disabled={executing || removing || deleting}
                        onItemClick={({ detail }) => {
                          if (detail.id === 'remove-selected') handleRemoveUsecases();
                          if (detail.id === 'delete-selected') setShowDeleteModal(true);
                          if (detail.id === 'add-usecases') navigate(`/applications/${id}/add-usecases`);
                        }}
                        items={[
                          { id: 'remove-selected', text: `Remove selected (${selectedUsecases.length})`, disabled: selectedUsecases.length === 0 },
                          { id: 'delete-selected', text: `Delete selected (${selectedUsecases.length})`, disabled: selectedUsecases.length === 0 },
                          { id: 'add-usecases', text: 'Add existing usecases' },
                        ]}
                        mainAction={{
                          text: `Execute selected (${selectedUsecases.length})`,
                          onClick: handleExecuteSelected,
                          disabled: selectedUsecases.length === 0,
                        }}
                      />
                    }
                  >
                    Usecases
                  </Header>
                }
                empty={
                  <Box textAlign="center" padding="l">
                    <SpaceBetween size="m">
                      <Box variant="p">No usecases associated with this application</Box>
                      <Button onClick={() => navigate(`/applications/${id}/add-usecases`)}>Add usecases</Button>
                    </SpaceBetween>
                  </Box>
                }
              />
            ),
          },
          {
            id: 'test-suites',
            label: `Test Suites (${testSuites.length})`,
            content: (
              <Container>
                <TestSuitesTable
                  items={testSuites}
                  header={
                    <Header
                      variant="h2"
                      actions={
                        <ButtonDropdown
                          variant="primary"
                          onItemClick={({ detail }) => {
                            if (detail.id === 'add-test-suites') navigate(`/applications/${id}/add-test-suites`);
                          }}
                          items={[
                            { id: 'add-test-suites', text: 'Add existing test suites' },
                          ]}
                          mainAction={{
                            text: 'Create test suite',
                            onClick: () => navigate(`/test-suites/create?applicationId=${id}`),
                          }}
                        />
                      }
                    >
                      Test Suites
                    </Header>
                  }
                  empty={
                    <Box textAlign="center" padding="l">
                      <SpaceBetween size="m">
                        <Box variant="p">No test suites associated with this application</Box>
                        <Button onClick={() => navigate(`/test-suites/create?applicationId=${id}`)}>Create test suite</Button>
                      </SpaceBetween>
                    </Box>
                  }
                />
              </Container>
            ),
          },
          {
            id: 'metrics',
            label: 'Metrics',
            content: <MetricsTab applicationId={id!} />,
          },
          {
            id: 'costs',
            label: 'Cost',
            // Renders nothing when the costs API answers 403/404 (same view guard as the metrics tab).
            content: <ApplicationCostCard applicationId={id!} />,
          },
        ]}
      />

    </SpaceBetween>
  );
}
