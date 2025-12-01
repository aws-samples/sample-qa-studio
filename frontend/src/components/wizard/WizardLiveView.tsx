import { useState } from 'react';
import SpaceBetween from "@cloudscape-design/components/space-between";
import Alert from "@cloudscape-design/components/alert";
import Spinner from "@cloudscape-design/components/spinner";
import Box from "@cloudscape-design/components/box";
import Badge from "@cloudscape-design/components/badge";
import Button from "@cloudscape-design/components/button";
import { RemoteBrowser } from '../dcv/DCVViewer';
import { useLiveViewUrl } from '../../hooks/useLiveViewUrl';
import './WizardLiveView.css';

interface WizardLiveViewProps {
  sessionId: string;
  usecaseId: string;
  pendingStep?: any;
  onAcceptStep: (stepId: string) => Promise<void>;
  onRejectStep: (stepId: string) => Promise<void>;
  acceptedStepsCount: number;
}

export default function WizardLiveView({ 
  sessionId, 
  usecaseId,
  pendingStep,
  onAcceptStep,
  onRejectStep,
  acceptedStepsCount
}: WizardLiveViewProps) {
  const [accepting, setAccepting] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  
  const { 
    liveViewUrl, 
    error, 
    isExpired, 
  } = useLiveViewUrl(usecaseId, sessionId, true); // Always poll for wizard

  const hasLiveView = liveViewUrl && !isExpired;
  
  const handleAccept = async () => {
    if (!pendingStep) return;
    
    setAccepting(true);
    try {
      const stepId = pendingStep.stepId || pendingStep.step_id || pendingStep.sk?.replace('EXECUTION_STEP#', '');
      await onAcceptStep(stepId);
    } finally {
      setAccepting(false);
    }
  };

  const handleReject = async () => {
    if (!pendingStep) return;
    
    setRejecting(true);
    try {
      const stepId = pendingStep.stepId || pendingStep.step_id || pendingStep.sk?.replace('EXECUTION_STEP#', '');
      await onRejectStep(stepId);
    } finally {
      setRejecting(false);
    }
  };
  
  const isStepCompleted = pendingStep && (pendingStep.actId || pendingStep.act_id) && pendingStep.status !== 'executing';
  
  // For wizard mode, treat "not found" as "still loading" rather than an error
  const isWaitingForLiveView = !hasLiveView && !isExpired;
  const hasRealError = error && !error.includes('404') && !error.includes('not found');

  return (
    <SpaceBetween direction="vertical" size="m">
      {/* Show spinner while waiting for live view */}
      {isWaitingForLiveView && (
        <Box textAlign="center" padding="l">
          <SpaceBetween direction="vertical" size="m" alignItems="center">
            <Spinner size="large" />
            <div>Starting browser session...</div>
            <Box variant="small" color="text-body-secondary">
              This usually takes 10-15 seconds
            </Box>
          </SpaceBetween>
        </Box>
      )}

      {/* Only show error for real errors (not 404) */}
      {hasRealError && (
        <Alert type="error">
          {error}
        </Alert>
      )}

      {/* Show expired message */}
      {isExpired && (
        <Alert type="warning">
          Live view session has expired. The wizard may have timed out.
        </Alert>
      )}

      {hasLiveView && (
        <div style={{ position: 'relative' }}>
          <div 
            data-dcv-container
            style={{ 
              width: '100%', 
              height: '600px',
              border: '1px solid var(--color-border-divider-default)',
              borderRadius: '8px',
              overflow: 'hidden',
              position: 'relative',
              backgroundColor: '#000'
            }}
          >
            <div style={{
              width: '100%',
              height: '100%',
              position: 'absolute',
              top: 0,
              left: 0
            }}>
              <RemoteBrowser presignedUrl={liveViewUrl} />
            </div>
            
            {/* Current step overlay at bottom - single line */}
            {pendingStep && (
              <div 
                style={{
                  position: 'absolute',
                  bottom: 0,
                  left: 0,
                  right: 0,
                  backgroundColor: 'rgba(0, 0, 0, 0.85)',
                  backdropFilter: 'blur(8px)',
                  padding: '8px 12px',
                  zIndex: 1001,
                  borderBottomLeftRadius: '8px',
                  borderBottomRightRadius: '8px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  color: 'white',
                  fontSize: '13px'
                }}
              >
                {isStepCompleted ? (
                  <Badge color="green">✓ Completed</Badge>
                ) : (
                  <Badge color="blue">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Spinner size="normal" />
                      <span>Executing</span>
                    </div>
                  </Badge>
                )}
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {pendingStep.instruction}
                </span>
                {isStepCompleted && (
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <Button
                      onClick={handleReject}
                      loading={rejecting}
                      disabled={accepting}
                      iconName="close"
                    >
                      Reject
                    </Button>
                    <Button
                      variant="primary"
                      onClick={handleAccept}
                      loading={accepting}
                      disabled={rejecting}
                      iconName="check"
                    >
                      Accept
                    </Button>
                  </div>
                )}
              </div>
            )}
            
            {/* Transparent overlay to prevent user interaction */}
            <div 
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: '100%',
                backgroundColor: 'transparent',
                zIndex: 1000,
                cursor: 'not-allowed'
              }}
              title="Browser is being controlled automatically. Interaction is disabled."
            />
          </div>
        </div>
      )}
    </SpaceBetween>
  );
}
