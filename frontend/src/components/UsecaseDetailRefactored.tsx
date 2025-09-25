import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Modal from "@cloudscape-design/components/modal";
import Box from "@cloudscape-design/components/box";
import Tabs from "@cloudscape-design/components/tabs";
import { LazyWrapper } from './common/LazyWrapper';
import { api } from '../utils/api';

// Lazy load components to reduce initial bundle size
const UsecaseHeader = React.lazy(() => import('./usecase/UsecaseHeader'));
const UsecaseInfo = React.lazy(() => import('./usecase/UsecaseInfo'));
const UsecaseSchedule = React.lazy(() => import('./usecase/UsecaseSchedule'));
const UsecaseVariables = React.lazy(() => import('./usecase/UsecaseVariables'));
const SecretsManager = React.lazy(() => import('./SecretsManager'));
const WorkflowSteps = React.lazy(() => import('./usecase/WorkflowSteps'));
const ExecutionHistory = React.lazy(() => import('./usecase/ExecutionHistory'));
const UsecaseHooks = React.lazy(() => import('./usecase/UsecaseHooks'));

export default function UsecaseDetailRefactored() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [activeTabId, setActiveTabId] = useState(searchParams.get('tab') || 'history');

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

      <LazyWrapper containerTitle="Use Case Information" loadingText="Loading usecase info...">
        <UsecaseInfo usecaseId={id} />
      </LazyWrapper>

      <Tabs
        activeTabId={activeTabId}
        onChange={({ detail }) => handleTabChange(detail.activeTabId)}
        tabs={[
          {
            id: 'history',
            label: 'Execution History',
            content: (
              <LazyWrapper loadingText="Loading executions...">
                <ExecutionHistory usecaseId={id} />
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