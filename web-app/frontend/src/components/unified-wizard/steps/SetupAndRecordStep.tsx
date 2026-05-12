import { useState, useEffect, useRef, useCallback } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import FormField from "@cloudscape-design/components/form-field";
import Select from "@cloudscape-design/components/select";
import Alert from "@cloudscape-design/components/alert";
import Box from "@cloudscape-design/components/box";
import Grid from "@cloudscape-design/components/grid";
import type { StepProps } from '../types';
import { api } from '../../../utils/api';
import { regionOptions, findRegionOptions } from '../../../utils/browser_regions';
import WizardLiveView from '../../wizard/WizardLiveView';
import WizardStepBuilder from '../../wizard/WizardStepBuilder';
import WizardStepsList from '../../wizard/WizardStepsList';

export default function SetupAndRecordStep({ state, dispatch, validationErrors }: StepProps) {
  const { interactiveConfig } = state;
  const [steps, setSteps] = useState<any[]>([]);
  const [currentStep, setCurrentStep] = useState<any | null>(null);

  // Ref for cleanup on unmount / beforeunload
  const sessionRef = useRef<{ sessionId: string; usecaseId: string } | null>(null);

  // Keep ref in sync with state
  useEffect(() => {
    if (interactiveConfig.sessionId && interactiveConfig.usecaseId) {
      sessionRef.current = {
        sessionId: interactiveConfig.sessionId,
        usecaseId: interactiveConfig.usecaseId,
      };
    } else {
      sessionRef.current = null;
    }
  }, [interactiveConfig.sessionId, interactiveConfig.usecaseId]);

  // Set default browser region from config if not set
  useEffect(() => {
    if (!interactiveConfig.browserRegion) {
      dispatch({
        type: 'UPDATE_INTERACTIVE_CONFIG',
        payload: { browserRegion: __APP_CONFIG__.defaultRegion },
      });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const terminateSession = useCallback(async (sessionId: string, usecaseId: string) => {
    try {
      await api.post(`wizard/${sessionId}/terminate/${usecaseId}`, {});
    } catch (err) {
      console.error('Failed to terminate session:', err);
    }
  }, []);

  // Cleanup on unmount and beforeunload
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (sessionRef.current) {
        terminateSession(sessionRef.current.sessionId, sessionRef.current.usecaseId);
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      // Terminate on unmount if session is still active
      if (sessionRef.current) {
        terminateSession(sessionRef.current.sessionId, sessionRef.current.usecaseId);
      }
    };
  }, [terminateSession]);

  // Poll for execution status and steps when session is active
  useEffect(() => {
    if (interactiveConfig.sessionStatus !== 'active' || !interactiveConfig.sessionId || !interactiveConfig.usecaseId) {
      return;
    }

    const pollInterval = setInterval(async () => {
      try {
        const stepsData = await api.get(
          `usecase/${interactiveConfig.usecaseId}/executions/${interactiveConfig.sessionId}/steps`
        );
        const sortedSteps = (stepsData.steps || []).sort((a: any, b: any) => a.sort - b.sort);
        setSteps(sortedSteps);

        const pendingStep = sortedSteps.find(
          (s: any) => s.acceptanceStatus === 'pending_acceptance' || s.acceptance_status === 'pending_acceptance'
        );
        setCurrentStep(pendingStep || null);
      } catch (err) {
        console.error('Error polling wizard steps:', err);
      }
    }, 2000);

    return () => clearInterval(pollInterval);
  }, [interactiveConfig.sessionStatus, interactiveConfig.sessionId, interactiveConfig.usecaseId]);

  const handleStartSession = async () => {
    if (!state.basicInfo.startingUrl.trim()) {
      return;
    }

    dispatch({
      type: 'UPDATE_INTERACTIVE_CONFIG',
      payload: { sessionStatus: 'starting', sessionError: null },
    });

    try {
      const response = await api.post('wizard/start', {
        name: state.basicInfo.name.trim() || 'Interactive Wizard Session',
        description: state.basicInfo.description.trim(),
        starting_url: state.basicInfo.startingUrl.trim(),
        tags: [],
        region: state.basicInfo.executionRegion,
      });

      if (!response?.sessionId || !response?.usecaseId) {
        throw new Error('Invalid response from server: missing sessionId or usecaseId');
      }

      dispatch({
        type: 'UPDATE_INTERACTIVE_CONFIG',
        payload: {
          sessionId: response.sessionId,
          usecaseId: response.usecaseId,
          sessionStatus: 'active',
          sessionError: null,
          isNavHidden: true,
        },
      });
    } catch (err: any) {
      console.error('Wizard start error:', err);
      dispatch({
        type: 'UPDATE_INTERACTIVE_CONFIG',
        payload: {
          sessionStatus: 'error',
          sessionError: err.message || 'Failed to start wizard session. Please try again.',
        },
      });
    }
  };

  const handleAddStep = async (stepData: any) => {
    if (!interactiveConfig.sessionId) return;

    try {
      await api.post(`wizard/${interactiveConfig.sessionId}/step`, stepData);

      // Immediate poll for updated steps
      if (interactiveConfig.usecaseId) {
        const stepsData = await api.get(
          `usecase/${interactiveConfig.usecaseId}/executions/${interactiveConfig.sessionId}/steps`
        );
        const sortedSteps = (stepsData.steps || []).sort((a: any, b: any) => a.sort - b.sort);
        setSteps(sortedSteps);

        const pendingStep = sortedSteps.find(
          (s: any) => s.acceptanceStatus === 'pending_acceptance' || s.acceptance_status === 'pending_acceptance'
        );
        setCurrentStep(pendingStep || null);
      }
    } catch (err: any) {
      console.error('Error adding step:', err);
      throw err;
    }
  };

  const handleAcceptStep = async (stepId: string) => {
    if (!interactiveConfig.sessionId || !interactiveConfig.usecaseId) return;
    await api.post(`wizard/${interactiveConfig.sessionId}/accept/${stepId}/${interactiveConfig.usecaseId}`, {});
  };

  const handleRejectStep = async (stepId: string) => {
    if (!interactiveConfig.sessionId || !interactiveConfig.usecaseId) return;
    await api.post(`wizard/${interactiveConfig.sessionId}/reject/${stepId}/${interactiveConfig.usecaseId}`, {});
  };

  const handleFinishRecording = async () => {
    // Terminate the session
    if (interactiveConfig.sessionId && interactiveConfig.usecaseId) {
      await terminateSession(interactiveConfig.sessionId, interactiveConfig.usecaseId);
    }

    dispatch({
      type: 'UPDATE_INTERACTIVE_CONFIG',
      payload: {
        sessionStatus: 'finished',
        isNavHidden: false,
        steps: acceptedSteps,
      },
    });

    // Advance to next step (Review)
    dispatch({ type: 'NEXT_STEP' });
  };

  const handleCancelSession = async () => {
    if (interactiveConfig.sessionId && interactiveConfig.usecaseId) {
      await terminateSession(interactiveConfig.sessionId, interactiveConfig.usecaseId);
    }

    dispatch({
      type: 'UPDATE_INTERACTIVE_CONFIG',
      payload: {
        sessionId: null,
        usecaseId: null,
        sessionStatus: 'idle',
        sessionError: null,
        isNavHidden: false,
        steps: [],
      },
    });
    setSteps([]);
    setCurrentStep(null);
  };

  const regions = regionOptions();
  const isSessionActive = interactiveConfig.sessionStatus === 'active';
  const isSessionStarting = interactiveConfig.sessionStatus === 'starting';
  const isSessionFinished = interactiveConfig.sessionStatus === 'finished';

  const acceptedSteps = steps.filter(
    (s) => s.acceptanceStatus === 'accepted' || s.acceptance_status === 'accepted'
  );
  const pendingStep = steps.find(
    (s) => s.acceptanceStatus === 'pending_acceptance' || s.acceptance_status === 'pending_acceptance'
  );

  // If session is active, render the live session view
  if (isSessionActive && interactiveConfig.sessionId && interactiveConfig.usecaseId) {
    return (
      <SpaceBetween direction="vertical" size="l">
        <Container
          header={
            <Header
              variant="h2"
              actions={
                <SpaceBetween direction="horizontal" size="xs">
                  <Button onClick={handleCancelSession}>Cancel Session</Button>
                  <Button variant="primary" onClick={handleFinishRecording}>
                    Finish Recording
                  </Button>
                </SpaceBetween>
              }
            >
              Interactive recording session
            </Header>
          }
        >
          <SpaceBetween direction="vertical" size="s">
            <Alert type="info">
              Build your test steps interactively. Add steps using the builder below, accept or reject
              them in the live view, then click "Finish Recording" when done.
            </Alert>
            <Box variant="small" color="text-body-secondary">
              Session: {interactiveConfig.sessionId} | Accepted steps: {acceptedSteps.length}
            </Box>
          </SpaceBetween>
        </Container>

        {/* Live View */}
        <WizardLiveView
          sessionId={interactiveConfig.sessionId}
          usecaseId={interactiveConfig.usecaseId}
          pendingStep={pendingStep}
          onAcceptStep={handleAcceptStep}
          onRejectStep={handleRejectStep}
          acceptedStepsCount={acceptedSteps.length}
        />

        {/* Step Builder */}
        <WizardStepBuilder
          onAddStep={handleAddStep}
          disabled={!!pendingStep}
          usecaseId={interactiveConfig.usecaseId}
          existingSteps={acceptedSteps}
        />

        {/* Accepted Steps List */}
        <WizardStepsList
          steps={acceptedSteps}
          usecaseId={interactiveConfig.usecaseId}
          sessionId={interactiveConfig.sessionId}
        />
      </SpaceBetween>
    );
  }

  // If session is finished, show summary
  if (isSessionFinished) {
    return (
      <Container>
        <SpaceBetween direction="vertical" size="l">
          <Alert type="success">
            Recording session completed with {interactiveConfig.steps?.length || 0} accepted step(s).
            Click "Next" to review and create your use case.
          </Alert>
          <Box>
            <Box variant="awsui-key-label">Starting URL</Box>
            <div>{state.basicInfo.startingUrl}</div>
          </Box>
          <Box>
            <Box variant="awsui-key-label">Region</Box>
            <div>{state.basicInfo.executionRegion}</div>
          </Box>
          <Box>
            <Box variant="awsui-key-label">Steps Recorded</Box>
            <div>{interactiveConfig.steps?.length || 0}</div>
          </Box>
        </SpaceBetween>
      </Container>
    );
  }

  // Default: setup form
  return (
    <Container>
      <SpaceBetween direction="vertical" size="l">
        <Alert type="info">
          The Interactive Wizard uses a live browser session. Select a browser
          region, then click "Start Session" to begin building your test steps interactively.
        </Alert>

        {interactiveConfig.sessionError && (
          <Alert
            type="error"
            dismissible
            onDismiss={() =>
              dispatch({
                type: 'UPDATE_INTERACTIVE_CONFIG',
                payload: { sessionError: null, sessionStatus: 'idle' },
              })
            }
          >
            {interactiveConfig.sessionError}
          </Alert>
        )}

        <Button
          variant="primary"
          onClick={handleStartSession}
          loading={isSessionStarting}
          disabled={!state.basicInfo.startingUrl.trim() || isSessionStarting}
        >
          Start Session
        </Button>
      </SpaceBetween>
    </Container>
  );
}
