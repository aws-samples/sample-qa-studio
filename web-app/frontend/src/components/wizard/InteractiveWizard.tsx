import { useState, useEffect } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import AppLayout from "@cloudscape-design/components/app-layout";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Container from "@cloudscape-design/components/container";
import Alert from "@cloudscape-design/components/alert";
import Spinner from "@cloudscape-design/components/spinner";
import Box from "@cloudscape-design/components/box";
import Modal from "@cloudscape-design/components/modal";
import Breadcrumb from '../common/Breadcrumb';
import { api } from '../../utils/api';
import WizardLiveView from './WizardLiveView';
import WizardStepBuilder from './WizardStepBuilder';
import WizardStepsList from './WizardStepsList';

interface WizardSession {
  sessionId: string;
  usecaseId: string;
  status: string;
  liveViewUrl?: string;
}

export default function InteractiveWizard() {
  const navigate = useNavigate();
  const { sessionId } = useParams();
  const location = useLocation();
  const [session, setSession] = useState<WizardSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [steps, setSteps] = useState<any[]>([]);
  const [currentStep, setCurrentStep] = useState<any | null>(null);
  const [showCloseModal, setShowCloseModal] = useState(false);
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [closing, setClosing] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const [fileModalVisible, setFileModalVisible] = useState(false);
  const [fileContent, setFileContent] = useState<{ url: string, title: string, fileType: string } | null>(null);

  // Initialize session from route params or location state
  useEffect(() => {
    if (location.state?.sessionId && location.state?.usecaseId) {
      setSession({
        sessionId: location.state.sessionId,
        usecaseId: location.state.usecaseId,
        status: 'initializing'
      });
      setLoading(false);
    } else if (sessionId) {
      // Try to load session from sessionId param (for page refresh)
      setSession({
        sessionId: sessionId,
        usecaseId: '', // Will be loaded from execution
        status: 'unknown'
      });
      setLoading(false);
    } else {
      setError('No session ID provided');
      setLoading(false);
    }
  }, [sessionId, location.state]);

  // Cleanup on unmount or page navigation
  useEffect(() => {
    if (!session || !session.usecaseId) return;

    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      // Show browser confirmation dialog
      e.preventDefault();
      e.returnValue = '';
      
      // Try to terminate session (may not complete before page closes)
      terminateSession().catch(err => console.error('Cleanup failed:', err));
    };

    // Add beforeunload listener
    window.addEventListener('beforeunload', handleBeforeUnload);

    // Cleanup on component unmount
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      
      // Terminate session when component unmounts (navigation away)
      if (session && session.usecaseId) {
        terminateSession().catch(err => console.error('Cleanup on unmount failed:', err));
      }
    };
  }, [session?.sessionId, session?.usecaseId]);

  // Poll for execution status and steps
  useEffect(() => {
    if (!session || !session.usecaseId) {
      console.log('Polling skipped - session or usecaseId not available', { session });
      return;
    }

    console.log('Starting polling for session:', session.sessionId, 'usecase:', session.usecaseId);

    const pollInterval = setInterval(async () => {
      try {
        // Get execution details
        const execution = await api.get(`usecase/${session.usecaseId}/executions/${session.sessionId}`);
        console.log('Execution data:', execution);
        
        // Get steps
        const stepsData = await api.get(`usecase/${session.usecaseId}/executions/${session.sessionId}/steps`);
        console.log('Steps data:', stepsData);
        
        const sortedSteps = (stepsData.steps || []).sort((a: any, b: any) => a.sort - b.sort);
        console.log('Sorted steps:', sortedSteps.length, sortedSteps);
        setSteps(sortedSteps);

        // Update current step if it's executing (check both camelCase and snake_case)
        const executingStep = sortedSteps.find((s: any) => 
          s.acceptanceStatus === 'pending_acceptance' || s.acceptance_status === 'pending_acceptance'
        );
        console.log('Pending step:', executingStep);
        setCurrentStep(executingStep || null);

        // Update session status and live view URL
        setSession(prev => {
          if (!prev) return null;
          
          const updates: any = { 
            ...prev, 
            status: execution.status 
          };
          
          // Update live view URL if available and not already set
          if (execution.live_view_url && !prev.liveViewUrl) {
            updates.liveViewUrl = execution.live_view_url;
          }
          
          return updates;
        });
      } catch (err) {
        console.error('Error polling wizard status:', err);
      }
    }, 2000); // Poll every 2 seconds

    return () => clearInterval(pollInterval);
  }, [session?.sessionId, session?.usecaseId]);

  const handleAddStep = async (stepData: any) => {
    if (!session) {
      console.error('No session available');
      return;
    }

    console.log('Adding step:', stepData, 'to session:', session.sessionId);

    try {
      setError(null);
      const response = await api.post(`wizard/${session.sessionId}/step`, stepData);
      
      console.log('Step added successfully:', response);
      
      // Trigger immediate poll to update UI faster
      if (session.usecaseId) {
        console.log('Polling for updated steps...');
        try {
          const stepsData = await api.get(`usecase/${session.usecaseId}/executions/${session.sessionId}/steps`);
          console.log('Steps after add:', stepsData);
          
          const sortedSteps = (stepsData.steps || []).sort((a: any, b: any) => a.sort - b.sort);
          setSteps(sortedSteps);
          
          const executingStep = sortedSteps.find((s: any) => 
            s.acceptanceStatus === 'pending_acceptance' || s.acceptance_status === 'pending_acceptance'
          );
          console.log('Found executing step:', executingStep);
          setCurrentStep(executingStep || null);
        } catch (pollErr) {
          console.error('Error in immediate poll:', pollErr);
        }
      }
    } catch (err: any) {
      console.error('Error adding step:', err);
      setError(err.message || 'Failed to add step');
    }
  };

  const handleAcceptStep = async (stepId: string) => {
    if (!session) return;

    try {
      setError(null);
      await api.post(`wizard/${session.sessionId}/accept/${stepId}/${session.usecaseId}`, {});
      
      // Update steps list via polling
    } catch (err: any) {
      setError(err.message || 'Failed to accept step');
    }
  };

  const handleRejectStep = async (stepId: string) => {
    if (!session) return;

    try {
      setError(null);
      await api.post(`wizard/${session.sessionId}/reject/${stepId}/${session.usecaseId}`, {});
      
      // Update steps list via polling
    } catch (err: any) {
      setError(err.message || 'Failed to reject step');
    }
  };

  const handleRestart = async () => {
    if (!session) return;

    try {
      setError(null);
      await api.post(`wizard/${session.sessionId}/restart`, {});
      
      // Clear current step
      setCurrentStep(null);
    } catch (err: any) {
      setError(err.message || 'Failed to restart wizard');
    }
  };

  const terminateSession = async () => {
    if (!session) return;

    try {
      await api.post(`wizard/${session.sessionId}/terminate/${session.usecaseId}`, {});
    } catch (err: any) {
      console.error('Failed to terminate session:', err);
      throw err;
    }
  };

  const handleClose = async () => {
    if (!session) return;

    setClosing(true);
    try {
      await terminateSession();
      
      // Navigate to use case detail
      navigate(`/usecase/${session.usecaseId}`);
    } catch (err: any) {
      setError(err.message || 'Failed to close wizard');
      setClosing(false);
    }
  };

  const handleCancel = async () => {
    if (!session) return;

    setCanceling(true);
    try {
      await terminateSession();
      
      // Navigate to home
      navigate('/');
    } catch (err: any) {
      setError(err.message || 'Failed to cancel wizard');
      setCanceling(false);
    }
  };

  if (loading || !session) {
    return (
      <AppLayout
        navigationHide
        toolsHide
        content={
          <SpaceBetween direction="vertical" size="l">
            <Breadcrumb
              items={[
                { text: "Home", href: "/" },
                { text: "Create Use Case", href: "/create" },
                { text: "Interactive Wizard" }
              ]}
            />
            
            <Header variant="h1">
              Interactive Use Case Builder
            </Header>

            <Container>
              <Box textAlign="center" padding="xxl">
                {loading ? (
                  <SpaceBetween direction="vertical" size="m" alignItems="center">
                    <Spinner size="large" />
                    <div>Initializing wizard session...</div>
                  </SpaceBetween>
                ) : error ? (
                  <SpaceBetween direction="vertical" size="m">
                    <Alert type="error">{error}</Alert>
                    <Button onClick={() => navigate('/create/wizard/setup')}>
                      Start New Wizard
                    </Button>
                  </SpaceBetween>
                ) : (
                  <SpaceBetween direction="vertical" size="m">
                    <div>
                      Build your use case interactively with live browser feedback.
                      Add steps one at a time, see them execute in real-time, and accept them when ready.
                    </div>
                    <Button
                      variant="primary"
                      onClick={() => navigate('/create/wizard/setup')}
                    >
                      Start Wizard
                    </Button>
                  </SpaceBetween>
                )}
              </Box>
            </Container>
          </SpaceBetween>
        }
      />
    );
  }

  const acceptedSteps = steps.filter(s => s.acceptanceStatus === 'accepted' || s.acceptance_status === 'accepted');
  const pendingStep = steps.find(s => s.acceptanceStatus === 'pending_acceptance' || s.acceptance_status === 'pending_acceptance');

  return (
    <AppLayout
      navigationHide
      toolsHide
      content={
        <SpaceBetween direction="vertical" size="l">
          <Breadcrumb
            items={[
              { text: "Home", href: "/" },
              { text: "Create Use Case", href: "/create" },
              { text: "Interactive Wizard" }
            ]}
          />

          <Header
            variant="h1"
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                <Button
                  onClick={() => setShowCancelModal(true)}
                  disabled={closing || canceling}
                >
                  Cancel
                </Button>
                <Button
                  iconName="refresh"
                  onClick={handleRestart}
                  disabled={acceptedSteps.length === 0 || closing || canceling}
                >
                  Restart
                </Button>
                <Button
                  variant="primary"
                  onClick={() => setShowCloseModal(true)}
                  disabled={closing || canceling}
                >
                  Finish & Save
                </Button>
              </SpaceBetween>
            }
          >
            Interactive Use Case Builder
          </Header>

          {error && (
            <Alert
              type="error"
              dismissible
              onDismiss={() => setError(null)}
            >
              {error}
            </Alert>
          )}

          {/* Live View */}
          <WizardLiveView
            sessionId={session.sessionId}
            usecaseId={session.usecaseId}
            pendingStep={pendingStep}
            onAcceptStep={handleAcceptStep}
            onRejectStep={handleRejectStep}
            acceptedStepsCount={acceptedSteps.length}
          />

          {/* Step Builder */}
          <WizardStepBuilder
            onAddStep={handleAddStep}
            disabled={!!pendingStep}
            usecaseId={session.usecaseId}
            existingSteps={acceptedSteps}
          />

          {/* Debug Info */}
          {process.env.NODE_ENV === 'development' && (
            <Container header={<Header variant="h3">Debug Info</Header>}>
              <SpaceBetween direction="vertical" size="xs">
                <div>Total steps: {steps.length}</div>
                <div>Accepted steps: {acceptedSteps.length}</div>
                <div>Pending step: {pendingStep ? 'Yes' : 'No'}</div>
                {steps.length > 0 && (
                  <Box variant="code">
                    {JSON.stringify(steps.map(s => ({
                      id: s.stepId || s.step_id,
                      instruction: s.instruction,
                      acceptanceStatus: s.acceptanceStatus || s.acceptance_status,
                      status: s.status,
                      actId: s.actId || s.act_id
                    })), null, 2)}
                  </Box>
                )}
              </SpaceBetween>
            </Container>
          )}

          {/* Accepted Steps List */}
          <WizardStepsList
            steps={acceptedSteps}
            usecaseId={session.usecaseId}
            sessionId={session.sessionId}
          />

          {/* Cancel Confirmation Modal */}
          <Modal
            onDismiss={() => setShowCancelModal(false)}
            visible={showCancelModal}
            header="Cancel Wizard"
            footer={
              <Box float="right">
                <SpaceBetween direction="horizontal" size="xs">
                  <Button
                    variant="link"
                    onClick={() => setShowCancelModal(false)}
                    disabled={canceling}
                  >
                    Keep Working
                  </Button>
                  <Button
                    onClick={handleCancel}
                    loading={canceling}
                  >
                    Cancel Wizard
                  </Button>
                </SpaceBetween>
              </Box>
            }
          >
            <SpaceBetween size="m">
              <Alert type="warning">
                This will stop the wizard session and discard all progress.
              </Alert>
              <Box>
                <p>Are you sure you want to cancel the wizard?</p>
                <p>
                  {acceptedSteps.length > 0 ? (
                    <>You have {acceptedSteps.length} accepted step{acceptedSteps.length !== 1 ? 's' : ''} that will be lost.</>
                  ) : (
                    <>No steps have been accepted yet.</>
                  )}
                </p>
                <p>
                  If you want to save your progress, click "Keep Working" and then use "Finish & Save" instead.
                </p>
              </Box>
            </SpaceBetween>
          </Modal>

          {/* Close Confirmation Modal */}
          <Modal
            onDismiss={() => setShowCloseModal(false)}
            visible={showCloseModal}
            header="Finish Wizard"
            footer={
              <Box float="right">
                <SpaceBetween direction="horizontal" size="xs">
                  <Button
                    variant="link"
                    onClick={() => setShowCloseModal(false)}
                    disabled={closing}
                  >
                    Keep Working
                  </Button>
                  <Button
                    variant="primary"
                    onClick={handleClose}
                    loading={closing}
                  >
                    Save & Close
                  </Button>
                </SpaceBetween>
              </Box>
            }
          >
            <SpaceBetween size="m">
              <Box>
                <p>Are you sure you want to finish the wizard?</p>
                <p>
                  Your use case will be saved with {acceptedSteps.length} accepted step{acceptedSteps.length !== 1 ? 's' : ''}.
                  You can continue editing it from the use case detail page.
                </p>
              </Box>
            </SpaceBetween>
          </Modal>

          {/* File Viewer Modal */}
          <Modal
            onDismiss={() => setFileModalVisible(false)}
            visible={fileModalVisible}
            size="max"
            header={fileContent?.title || 'File Viewer'}
          >
            {fileContent && (
              <iframe
                src={fileContent.url}
                style={{
                  width: '100%',
                  height: '80vh',
                  border: 'none'
                }}
                title={fileContent.title}
              />
            )}
          </Modal>
        </SpaceBetween>
      }
    />
  );
}
