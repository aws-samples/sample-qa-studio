import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Modal from "@cloudscape-design/components/modal";
import Box from "@cloudscape-design/components/box";
import AppLayout from "@cloudscape-design/components/app-layout";
import Grid from "@cloudscape-design/components/grid";
import { api } from '../utils/api';
import ExecutionTimeline from './common/ExecutionTimeline';
import Breadcrumb from './common/Breadcrumb';
import { ExecutionInformation, ExecutionSteps, ExecutionVariables } from './execution';
import LiveViewPanel from './execution/LiveViewPanel';
import { RecordingPlayer } from './RecordingPlayer';
import DownloadedFiles from './execution/DownloadedFiles';

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

export default function ExecutionDetailRefactored() {
  const { usecaseId, executionId } = useParams();
  const [execution, setExecution] = useState<any>(null);
  const [usecase, setUsecase] = useState<any>(null);
  const [executionSteps, setExecutionSteps] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalVisible, setModalVisible] = useState(false);
  const [modalContent, setModalContent] = useState<{ url: string, title: string, fileType?: string } | null>(null);
  const [recordingModalVisible, setRecordingModalVisible] = useState(false);
  const [stopModalVisible, setStopModalVisible] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [stopError, setStopError] = useState<string | null>(null);
  const [hasVariables, setHasVariables] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const fetchData = async () => {
    setRefreshTrigger(prev => prev + 1);
    try {
      const [executionData, stepsData, variablesData, usecaseData] = await Promise.all([
        api.get(`usecase/${usecaseId}/executions/${executionId}`),
        api.get(`usecase/${usecaseId}/executions/${executionId}/steps`),
        api.get(`usecase/${usecaseId}/executions/${executionId}/variables`).catch(() => ({ variables: [], runtime_variables: [] })),
        api.get(`usecase/${usecaseId}`)
      ]);

      setExecution(executionData);
      setUsecase(usecaseData);

      // Sort steps by sort property and set them
      const sortedSteps = (stepsData.steps || []).sort((a: any, b: any) => a.sort - b.sort);
      setExecutionSteps(sortedSteps);

      sortedSteps.forEach((step: any) => {
        if (step.logs.length > 0) {
          // step.logs = step.logs.reverse();
        }
      });

      // Check if there are any variables
      setHasVariables(variablesData?.variables?.length > 0 || variablesData?.runtime_variables?.length > 0);
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

    if (execution?.status === 'executing' || execution?.status === 'pending') {
      intervalId = setInterval(() => {
        fetchData();
      }, 10000); // 10 seconds
    }

    // Cleanup interval on unmount or when status changes
    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [execution?.status, usecaseId, executionId]);

  const handleViewContent = (content: { url: string, title: string, fileType: string }) => {
    setModalContent(content);
    setModalVisible(true);
  };

  const handleViewRecording = () => {
    setRecordingModalVisible(true);
  };

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

  if (loading) return <div>Loading...</div>;
  if (!execution) return <div>Execution not found</div>;
  if (!usecaseId || !executionId) return <div>Invalid parameters</div>;

  return (
    <AppLayout
      navigationHide
      toolsHide
      content={
        <SpaceBetween direction="vertical" size="l">
          <Breadcrumb
            items={[
              { text: "Home", href: "/" },
              { text: usecase?.name || "Use Case", href: `/usecase/${usecaseId}` },
              { text: "Execution Details" }
            ]}
          />
          <Header 
            variant="h1"
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                {execution?.cloudWatchLogsUrl && (
                  <Button
                    iconName="external"
                    onClick={() => window.open(execution.cloudWatchLogsUrl, '_blank')}
                  >
                    CloudWatch Logs
                  </Button>
                )}
                {(execution?.status === 'executing' || execution?.status === 'pending') && (
                  <Button
                    iconName="status-stopped"
                    onClick={() => setStopModalVisible(true)}
                  >
                    Stop Execution
                  </Button>
                )}
              </SpaceBetween>
            }
          >
            Execution Details
          </Header>

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
                onViewRecording={handleViewRecording}
              />

              {hasVariables && (
                <ExecutionVariables
                  usecaseId={usecaseId}
                  executionId={executionId}
                />
              )}
            </SpaceBetween>

            <SpaceBetween direction='vertical' size='m'>
              <ExecutionTimeline execution={execution} />
              {/* Live View Panel - Show for executing or recently completed executions */}
              {(execution?.status === 'executing') && (
                <LiveViewPanel
                  usecaseId={usecaseId}
                  executionId={executionId}
                  executionStatus={execution?.status}
                  currentStep={getCurrentStep(executionSteps)}
                />
              )}
            </SpaceBetween>
          </Grid>

          <ExecutionSteps
            executionSteps={executionSteps}
            usecaseId={usecaseId}
            executionId={executionId}
            onViewFile={handleViewContent}
          />

          <DownloadedFiles
            usecaseId={usecaseId}
            executionId={executionId}
            refreshTrigger={refreshTrigger}
          />

          {/* Modal for viewing files */}
          <Modal
            onDismiss={() => setModalVisible(false)}
            visible={modalVisible}
            size="max"
            header={modalContent?.title || "View File"}
            footer={
              <Box float="right">
                <SpaceBetween direction="horizontal" size="xs">
                  <Button variant="link" onClick={() => setModalVisible(false)}>
                    Close
                  </Button>
                  {modalContent?.url && (
                    <Button
                      variant="primary"
                      onClick={() => window.open(modalContent.url, '_blank')}
                      iconName="external"
                    >
                      Open in New Tab
                    </Button>
                  )}
                </SpaceBetween>
              </Box>
            }
          >
            {modalContent?.url && (
              <iframe
                src={modalContent.url}
                style={{
                  width: '100%',
                  height: '80vh',
                  border: 'none',
                  borderRadius: '4px'
                }}
                title={modalContent.title}
              />
            )}
          </Modal>

          {/* Modal for viewing recording */}
          <Modal
            onDismiss={() => setRecordingModalVisible(false)}
            visible={recordingModalVisible}
            size="max"
            header="Session Recording"
            footer={
              <Box float="right">
                <Button variant="link" onClick={() => setRecordingModalVisible(false)}>
                  Close
                </Button>
              </Box>
            }
          >
            {recordingModalVisible && (
              <RecordingPlayer
                usecaseId={usecaseId}
                executionId={executionId}
              />
            )}
          </Modal>

          {/* Stop Execution Confirmation Modal */}
          <Modal
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
      }
    />
  );
}