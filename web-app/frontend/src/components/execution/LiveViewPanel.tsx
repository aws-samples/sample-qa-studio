import React from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Alert from "@cloudscape-design/components/alert";
import Spinner from "@cloudscape-design/components/spinner";
import Box from "@cloudscape-design/components/box";
import Badge from "@cloudscape-design/components/badge";
import { RemoteBrowser } from '../dcv/DCVViewer';
import { useLiveViewUrl } from '../../hooks/useLiveViewUrl';

interface LiveViewPanelProps {
  usecaseId: string;
  executionId: string;
  executionStatus?: string;
  currentStep?: {
    sort: number;
    instruction: string;
    status: string;
  } | null;
}

export default function LiveViewPanel({ 
  usecaseId, 
  executionId,
  executionStatus = 'unknown',
  currentStep = null
}: LiveViewPanelProps) {
  const { 
    liveViewUrl, 
    isLoading, 
    error, 
    isExpired, 
  } = useLiveViewUrl(usecaseId, executionId, executionStatus === 'executing');

  const isExecutionActive = executionStatus === 'executing';
  const hasLiveView = liveViewUrl && !isExpired;
  
  // For execution mode, treat "not found" as "still loading" rather than an error
  const isWaitingForLiveView = !hasLiveView && !isExpired && isExecutionActive;
  const hasRealError = error && !error.includes('404') && !error.includes('not found');

  return (
    <Container
      header={
        <Header variant="h3">
          Live Browser View
        </Header>
      }
    >
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
            Live view session has expired. Live sessions are available for 24 hours after creation.
          </Alert>
        )}

        {/* Show info when execution is not active */}
        {!isExecutionActive && !hasLiveView && (
          <Alert type="info">
            No live view session available. Live view is only available during active executions.
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
              
              {/* Current step overlay at bottom */}
              {currentStep && (
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
                  {currentStep.status === 'executing' ? (
                    <Badge color="blue">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Spinner size="normal" />
                        <span>Executing</span>
                      </div>
                    </Badge>
                  ) : (
                    <Badge color="green">✓ Completed</Badge>
                  )}
                  <span style={{ fontWeight: 600 }}>Step {currentStep.sort}:</span>
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {currentStep.instruction}
                  </span>
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
    </Container>
  );
}