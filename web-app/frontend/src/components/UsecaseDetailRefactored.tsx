import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Modal from "@cloudscape-design/components/modal";
import Box from "@cloudscape-design/components/box";
import Tabs from "@cloudscape-design/components/tabs";
import Grid from "@cloudscape-design/components/grid";
import SplitPanel from "@cloudscape-design/components/split-panel";
import { LazyWrapper } from './common/LazyWrapper';
import { SPLIT_PANEL_I18N, useSplitPanel } from './common/splitPanel';
import { api } from '../utils/api';

// Lazy load components to reduce initial bundle size
const UsecaseHeader = React.lazy(() => import('./usecase/UsecaseHeader'));
const UsecaseInfo = React.lazy(() => import('./usecase/UsecaseInfo'));
const UsecaseCostCard = React.lazy(() => import('./common/cost/UsecaseCostCard'));
const UsecaseSchedule = React.lazy(() => import('./usecase/UsecaseSchedule'));
const UsecaseVariables = React.lazy(() => import('./usecase/UsecaseVariables'));
const SecretsManager = React.lazy(() => import('./SecretsManager'));
const HeadersManager = React.lazy(() => import('./HeadersManager'));
const WorkflowSteps = React.lazy(() => import('./usecase/WorkflowSteps'));
const ExecutionHistory = React.lazy(() => import('./usecase/ExecutionHistory'));
const UsecaseHooks = React.lazy(() => import('./usecase/UsecaseHooks'));
const ExecutionDetailPanel = React.lazy(() => import('./execution/ExecutionDetailPanel'));

const HISTORY_TAB = 'history';

export default function UsecaseDetailRefactored() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [activeTabId, setActiveTabId] = useState(searchParams.get('tab') || HISTORY_TAB);

  useEffect(() => {
    const tabFromUrl = searchParams.get('tab');
    if (tabFromUrl && tabFromUrl !== activeTabId) {
      setActiveTabId(tabFromUrl);
    }
  }, [searchParams]);

  // The selected execution lives in the URL (`?tab=<tab>&execution=<id>`): deep links,
  // refresh and the back button land on the open panel. It is independent of the tab, so
  // the Workflow Steps tab can be read next to the execution's steps in the panel.
  const selectedExecutionId = searchParams.get('execution');

  // Tab changes carry the selected execution along; only `execution` itself opens/closes the panel.
  const handleTabChange = (tabId: string) => {
    setActiveTabId(tabId);
    setSearchParams(selectedExecutionId ? { tab: tabId, execution: selectedExecutionId } : { tab: tabId });
  };

  // `replace` so clicking through rows does not pile up history entries. The current tab is kept.
  const handleSelectExecution = useCallback((executionId: string | null) => {
    setSearchParams(
      executionId ? { tab: activeTabId, execution: executionId } : { tab: activeTabId },
      { replace: true }
    );
  }, [setSearchParams, activeTabId]);

  const handlePanelToggle = useCallback((open: boolean) => {
    if (!open) handleSelectExecution(null);
  }, [handleSelectExecution]);

  // Memoised so the panel is re-registered only when the selection changes, not on every render.
  const executionPanel = useMemo(() => {
    if (!id || !selectedExecutionId) return null;
    return (
      <SplitPanel header={`Execution ${selectedExecutionId}`} i18nStrings={SPLIT_PANEL_I18N} closeBehavior="hide">
        <LazyWrapper loadingText="Loading execution...">
          <ExecutionDetailPanel key={selectedExecutionId} usecaseId={id} executionId={selectedExecutionId} />
        </LazyWrapper>
      </SplitPanel>
    );
  }, [id, selectedExecutionId]);

  useSplitPanel({ panel: executionPanel, open: Boolean(selectedExecutionId), onToggle: handlePanelToggle });

  if (!id) {
    return <div>Usecase ID not found</div>;
  }

  const handleDeleteUsecase = async () => {
    setDeleting(true);
    try {
      await api.delete(`usecase/${id}`);
      navigate('/');
    } catch (error) {
      console.error('Failed to delete usecase:', error);
    } finally {
      setDeleting(false);
      setShowDeleteModal(false);
    }
  };

  return (
    <SpaceBetween direction="vertical" size="l">
      <LazyWrapper loadingText="Loading header...">
        <UsecaseHeader usecaseId={id} onDeleteUsecase={() => setShowDeleteModal(true)} />
      </LazyWrapper>

      <Grid
        gridDefinition={[
          { colspan: { default: 12, m: 9 } },
          { colspan: { default: 12, m: 3 } },
        ]}
      >
        <LazyWrapper containerTitle="Use Case Information" loadingText="Loading usecase info...">
          <UsecaseInfo usecaseId={id} />
        </LazyWrapper>

        {/* Renders nothing when the costs API answers 403/404; the info column then keeps its width. */}
        <LazyWrapper containerTitle="Cost" loadingText="Loading cost...">
          <UsecaseCostCard usecaseId={id} />
        </LazyWrapper>
      </Grid>

      <Tabs
        activeTabId={activeTabId}
        onChange={({ detail }) => handleTabChange(detail.activeTabId)}
        tabs={[
          {
            id: HISTORY_TAB,
            label: 'Execution History',
            content: (
              <LazyWrapper loadingText="Loading executions...">
                <ExecutionHistory
                  usecaseId={id}
                  selectedExecutionId={selectedExecutionId}
                  onSelectExecution={handleSelectExecution}
                />
              </LazyWrapper>
            )
          },
          {
            id: 'steps',
            label: 'Workflow Steps',
            content: (
              <LazyWrapper loadingText="Loading steps...">
                <WorkflowSteps usecaseId={id} />
              </LazyWrapper>
            )
          },
          {
            id: 'schedule',
            label: 'Schedule',
            content: (
              <LazyWrapper loadingText="Loading schedule...">
                <UsecaseSchedule usecaseId={id} />
              </LazyWrapper>
            )
          },
          {
            id: 'variables',
            label: 'Variables',
            content: (
              <LazyWrapper loadingText="Loading variables...">
                <UsecaseVariables usecaseId={id} />
              </LazyWrapper>
            )
          },
          {
            id: 'secrets',
            label: 'Secrets',
            content: (
              <LazyWrapper loadingText="Loading secrets...">
                <SecretsManager usecaseId={id} />
              </LazyWrapper>
            )
          },
          {
            id: 'headers',
            label: 'Headers',
            content: (
              <LazyWrapper loadingText="Loading headers...">
                <HeadersManager usecaseId={id} />
              </LazyWrapper>
            )
          },
          {
            id: 'hooks',
            label: 'Hooks',
            content: (
              <LazyWrapper loadingText="Loading hooks...">
                <UsecaseHooks usecaseId={id} />
              </LazyWrapper>
            )
          }
        ]}
      />

      <Modal
        onDismiss={() => setShowDeleteModal(false)}
        visible={showDeleteModal}
        closeAriaLabel="Close modal"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setShowDeleteModal(false)}>
                Cancel
              </Button>
              <Button 
                variant="primary" 
                onClick={handleDeleteUsecase}
                loading={deleting}
                disabled={deleting}
              >
                {deleting ? 'Deleting...' : 'Delete'}
              </Button>
            </SpaceBetween>
          </Box>
        }
        header="Delete use case"
      >
        <SpaceBetween direction="vertical" size="m">
          <Box variant="span">
            Are you sure you want to delete this use case? This action cannot be undone.
          </Box>
          <Box variant="span">
            All associated steps, executions, schedules, and configurations will be permanently removed.
          </Box>
        </SpaceBetween>
      </Modal>
    </SpaceBetween>
  );
}