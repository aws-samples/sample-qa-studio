import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from "@cloudscape-design/components/header";
import Button from "@cloudscape-design/components/button";
import ButtonDropdown from "@cloudscape-design/components/button-dropdown";
import SpaceBetween from "@cloudscape-design/components/space-between";
import { api, exportImportApi } from '../../utils/api';
import { useApiData } from '../common/useAsyncData';
import { HeaderLoading } from '../common/LoadingStates';
import Breadcrumb from '../common/Breadcrumb';
import SubscriptionButton from './SubscriptionButton';
import { ELECTRON_CI_RUNNER_ONLY_MESSAGE, PlatformBadge, supportsCloudExecution } from '../common/platform';

interface UsecaseHeaderProps {
  usecaseId: string;
  onDeleteUsecase?: () => void;
}

export default function UsecaseHeader({ usecaseId, onDeleteUsecase }: UsecaseHeaderProps) {
  const navigate = useNavigate();
  const [executing, setExecuting] = useState(false);

  const { data: usecase, loading } = useApiData(
    () => api.get(`usecase/${usecaseId}`),
    [usecaseId]
  );

  const handleExecute = async (triggerType: string = 'OnDemandHeadless') => {
    setExecuting(true);
    try {
      await api.post(`usecase/${usecaseId}/execute?trigger-type=${triggerType}`, {});
    } catch (error) {
      console.error('Failed to execute usecase:', error);
    } finally {
      setExecuting(false);
    }
  };

  const handleExportUsecase = async () => {
    try {
      const blob = await exportImportApi.exportUsecase(usecaseId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = `usecase-${usecase?.name || 'export'}-export.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Failed to export usecase:', error);
    }
  };

  if (loading) {
    return <HeaderLoading variant="h1" text="Loading usecase..." />;
  }

  // Electron usecases are launched on the CI runner's host; the cloud
  // worker cannot run them, so every cloud trigger is disabled with the
  // same explanation the API returns.
  const cloudExecution = supportsCloudExecution(usecase?.test_platform);
  const cloudDisabledReason = cloudExecution ? undefined : ELECTRON_CI_RUNNER_ONLY_MESSAGE;

  return (
    <SpaceBetween direction="vertical" size="s">
      <Breadcrumb
        items={[
          { text: "Home", href: "/" },
          { text: usecase?.name || "Use Case" }
        ]}
      />
      <Header
        variant="h1"
        actions={
          <SpaceBetween direction="horizontal" size="m">
            <SubscriptionButton usecaseId={usecaseId} />
            <ButtonDropdown
              variant="primary"
              loading={executing}
              disabled={executing}
              onItemClick={({ detail }) => {
                if (detail.id === 'export') {
                  handleExportUsecase();
                } else if (detail.id === 'clone') {
                  navigate(`/create/new?path=clone&sourceId=${encodeURIComponent(usecaseId)}`);
                } else if (detail.id === 'delete') {
                  onDeleteUsecase?.();
                } else {
                  handleExecute(detail.id);
                }
              }}
              items={[
                {
                  text: "Admin",
                  items: [
                    {
                      id: "clone",
                      text: "Clone Use Case"
                    },
                    {
                      id: "export",
                      text: "Export Usecase"
                    },
                    {
                      id: "delete",
                      text: "Delete Use Case"
                    },
                  ]
                },
              ]}
              mainAction={{
                text: executing ? 'Starting Execution...' : 'Trigger Execution ',
                onClick: () => handleExecute('OnDemandHeadless'),
                disabled: !cloudExecution,
                disabledReason: cloudDisabledReason,
              }}
            />
          </SpaceBetween>
        }
      >
        <SpaceBetween direction="horizontal" size="s" alignItems="center">
          <span>{usecase?.name || 'Unknown Usecase'}</span>
          <PlatformBadge platform={usecase?.test_platform} />
        </SpaceBetween>
      </Header>
    </SpaceBetween>
  );
}