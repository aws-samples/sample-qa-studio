import { useState, useEffect } from 'react';
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Modal from "@cloudscape-design/components/modal";
import Box from "@cloudscape-design/components/box";
import Grid from "@cloudscape-design/components/grid";
import Container from "@cloudscape-design/components/container";
import KeyValuePairs from "@cloudscape-design/components/key-value-pairs";
import Spinner from "@cloudscape-design/components/spinner";
import { api, type ExecutionVariablesResponse } from '../../utils/api';
import ExecutionTimeline from '../common/ExecutionTimeline';
import { supportsLiveView } from '../common/platform';
import LogViewer from '../common/LogViewer';
import ExecutionInformation from './ExecutionInformation';
import ExecutionSteps from './ExecutionSteps';
import ExecutionVariables from './ExecutionVariables';
import LiveViewPanel from './LiveViewPanel';
import DownloadedFiles from './DownloadedFiles';

interface ExecutionDetailPanelProps {
  usecaseId: string;
  executionId: string;
}

const POLL_INTERVAL_MS = 10000;

/** Used when `/variables` fails, so the Variables card stays hidden and the badges resolve nothing. */
const EMPTY_VARIABLES: ExecutionVariablesResponse = { variables: [], runtime_variables: [], execution_variables: {} };

// Helper function to get the current executing step or the last completed step
function getCurrentStep(steps: any[]) {
  if (!steps || steps.length === 0) return null;

  // First, try to find a step that's currently executing
  const executingStep = steps.find(step => step.status === 'executing');
  if (executingStep) {
    return {
      sort: executingStep.sort,
      instruction: executingStep.instruction,
      status: executingStep.status
    };
  }

  // If no executing step, find the last completed step
  const completedSteps = steps.filter(step =>
    step.status === 'success' || step.status === 'completed'
  );

  if (completedSteps.length > 0) {
    const lastCompleted = completedSteps[completedSteps.length - 1];
    return {
      sort: lastCompleted.sort,
      instruction: lastCompleted.instruction,
      status: lastCompleted.status
    };
  }

  // If no completed steps, return the first pending step
  const pendingStep = steps.find(step => step.status === 'pending');
  if (pendingStep) {
    return {
      sort: pendingStep.sort,
      instruction: pendingStep.instruction,
      status: pendingStep.status
    };
  }

  return null;
}

/**
 * Everything of an execution view except the page chrome (layout, breadcrumb, h1):
 * information, Device Farm block, variables, timeline, live view, steps, downloaded
 * files, ci_runner logs, CloudWatch Logs / Stop actions and the stop confirmation.
 * Polls every 10 s while the execution is running or pending.
 */
export default function ExecutionDetailPanel({ usecaseId, executionId }: ExecutionDetailPanelProps) {
  const [execution, setExecution] = useState<any>(null);
  const [executionSteps, setExecutionSteps] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [stopModalVisible, setStopModalVisible] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [stopError, setStopError] = useState<string | null>(null);
  const [variables, setVariables] = useState<ExecutionVariablesResponse | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [logDownloadUrl, setLogDownloadUrl] = useState<string | null>(null);
  const [logArtifactsLoading, setLogArtifactsLoading] = useState(true);

  const fetchData = async () => {
    setRefreshTrigger(prev => prev + 1);
    try {
      const [executionData, stepsData, variablesData] = await Promise.all([
        api.get(`usecase/${usecaseId}/executions/${executionId}`),
        api.get(`usecase/${usecaseId}/executions/${executionId}/steps`),
        api.get(`usecase/${usecaseId}/executions/${executionId}/variables`).catch(() => EMPTY_VARIABLES),
      ]);

      setExecution(executionData);

      // Sort steps by sort property and set them
      const sortedSteps = (stepsData.steps || []).sort((a: any, b: any) => a.sort - b.sort);
      setExecutionSteps(sortedSteps);

      // One fetch per poll cycle feeds both the Variables card and the steps table.
      setVariables(variablesData);
    } catch (error) {
      console.error('Failed to fetch execution data:', error);
    } finally {
      setLoading(false);
    }
  };

  // Initial data fetch
  useEffect(() => {
    fetchData();
  }, [usecaseId, executionId]);

  // Polling effect for executing status
  useEffect(() => {
    let intervalId: NodeJS.Timeout | null = null;

    if (execution?.status === 'running' || execution?.status === 'pending') {
      intervalId = setInterval(() => {
        fetchData();
      }, POLL_INTERVAL_MS);
    }

    // Cleanup interval on unmount or when status changes
    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [execution?.status, usecaseId, executionId]);

  // Fetch usecase execution log artifact (only for ci_runner executions)
  useEffect(() => {
    const fetchLogArtifact = async () => {
      try {
        setLogArtifactsLoading(true);
        const data = await api.get(`usecase/${usecaseId}/executions/${executionId}/artifacts`);
        const logArtifact = (data.artifacts || []).find(
          (a: any) => a.type === 'logs'
        );
        setLogDownloadUrl(logArtifact?.download_url ?? null);
      } catch (error) {
        // Endpoint may not exist yet — gracefully degrade
        console.error('Failed to fetch execution artifacts:', error);
        setLogDownloadUrl(null);
      } finally {
        setLogArtifactsLoading(false);
      }
    };

    // Only fetch logs for ci_runner executions in terminal state
    const isCiRunner = execution?.trigger_type === 'ci_runner';
    const isTerminal = execution && execution.status !== 'running' && execution.status !== 'pending';
    if (isCiRunner && isTerminal) {
      fetchLogArtifact();
    } else if (execution) {
      // Not a ci_runner execution — skip log fetching
      setLogArtifactsLoading(false);
      setLogDownloadUrl(null);
    }
  }, [usecaseId, executionId, execution?.status, execution?.trigger_type]);

  const handleStopExecution = async () => {
    setStopping(true);
    setStopError(null);

    try {
      await api.post(`usecase/${usecaseId}/executions/${executionId}/stop`, {});
      setStopModalVisible(false);
      fetchData(); // Refresh execution data
    } catch (error: any) {
      console.error('Failed to stop execution:', error);
      setStopError(error?.message || 'Failed to stop execution. Please try again.');
    } finally {
      setStopping(false);
    }
  };

  if (loading) {
    return (
      <Box textAlign="center" padding="l">
        <Spinner size="large" />
      </Box>
    );
  }
  if (!execution) return <Box>Execution not found</Box>;

  const isActive = execution.status === 'running' || execution.status === 'pending';
  const showActions = Boolean(execution.cloudwatch_logs_url) || isActive;
  // The card shows the run's snapshot and captured values; current use-case variables do not count.
  const hasVariables = Object.keys(variables?.execution_variables ?? {}).length > 0
    || (variables?.runtime_variables?.length ?? 0) > 0;

  return (
    <SpaceBetween direction="vertical" size="l">
      {showActions && (
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            {execution.cloudwatch_logs_url && (
              <Button
                data-testid="cloudwatch-logs-button"
                iconName="external"
                onClick={() => window.open(execution.cloudwatch_logs_url, '_blank')}
              >
                CloudWatch Logs
              </Button>
            )}
            {isActive && (
              <Button
                data-testid="stop-execution-button"
                iconName="status-stopped"
                onClick={() => setStopModalVisible(true)}
              >
                Stop Execution
              </Button>
            )}
          </SpaceBetween>
        </Box>
      )}

      <Grid
        gridDefinition={[
          { colspan: { default: 12, m: 9 } },
          { colspan: { default: 12, m: 3 } },
        ]}
      >
        <SpaceBetween direction='vertical' size='m'>
          <ExecutionInformation
            execution={execution}
            usecaseId={usecaseId}
            executionId={executionId}
          />

          {execution.test_platform === 'mobile' && (
            <Container header={<Header variant="h2">Device Farm Details</Header>}>
              <KeyValuePairs
                columns={2}
                items={[
                  {
                    label: "Session ARN",
                    value: execution.device_farm_session_arn || '-',
                  },
                  {
                    label: "Device name",
                    value: execution.device_name || '-',
                  },
                  {
                    label: "OS version",
                    value: execution.device_os_version || '-',
                  },
                ]}
              />
            </Container>
          )}

          {variables && hasVariables && <ExecutionVariables variables={variables} />}
        </SpaceBetween>

        <SpaceBetween direction='vertical' size='m'>
          <ExecutionTimeline execution={execution} />
        </SpaceBetween>
      </Grid>

      {/* Live View Panel - Full width above steps table (web only: mobile runs on Device Farm, electron on the CI runner) */}
      {execution.status === 'running' && supportsLiveView(execution.test_platform) && (
        <LiveViewPanel
          usecaseId={usecaseId}
          executionId={executionId}
          executionStatus={execution.status}
          currentStep={getCurrentStep(executionSteps)}
        />
      )}

      <ExecutionSteps
        executionSteps={executionSteps}
        usecaseId={usecaseId}
        executionId={executionId}
        variables={variables}
        execution={execution}
      />

      <DownloadedFiles
        usecaseId={usecaseId}
        executionId={executionId}
        refreshTrigger={refreshTrigger}
        executionRegion={execution.region}
      />

      {/* Execution Logs (ci_runner only) */}
      {execution.trigger_type === 'ci_runner' && (logArtifactsLoading || logDownloadUrl) && (
        <Container
          header={<Header variant="h2">Execution Logs</Header>}
        >
          <LogViewer downloadUrl={logDownloadUrl} loading={logArtifactsLoading} />
        </Container>
      )}

      {/* Stop Execution Confirmation Modal */}
      <Modal
        data-testid="stop-execution-modal"
        onDismiss={() => setStopModalVisible(false)}
        visible={stopModalVisible}
        header="Stop Execution"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button
                variant="link"
                onClick={() => setStopModalVisible(false)}
                disabled={stopping}
              >
                Cancel
              </Button>
              <Button
                data-testid="confirm-stop-button"
                variant="primary"
                onClick={handleStopExecution}
                loading={stopping}
              >
                Stop Execution
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <SpaceBetween size="m">
          {stopError && (
            <Box color="text-status-error">
              {stopError}
            </Box>
          )}
          <Box>
            <p>Are you sure you want to stop this execution?</p>
            <p>This will terminate the running ECS task and mark the execution as stopped. This action cannot be undone.</p>
          </Box>
        </SpaceBetween>
      </Modal>
    </SpaceBetween>
  );
}
