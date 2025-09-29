import React, { useState } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import Button from "@cloudscape-design/components/button";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Alert from "@cloudscape-design/components/alert";
import Spinner from "@cloudscape-design/components/spinner";
import Modal from "@cloudscape-design/components/modal";
import Box from "@cloudscape-design/components/box";
import Link from "@cloudscape-design/components/link";
import { RemoteBrowser } from '../dcv/DCVViewer';
import { useLiveViewUrl } from '../../hooks/useLiveViewUrl';

interface LiveViewPanelProps {
  usecaseId: string;
  executionId: string;
  executionStatus?: string;
}

export default function LiveViewPanel({ 
  usecaseId, 
  executionId,
  executionStatus = 'unknown'
}: LiveViewPanelProps) {
  const [showViewer, setShowViewer] = useState(false);
  const [dcvError, setDcvError] = useState<string | null>(null);
  
  const { 
    liveViewUrl, 
    isLoading, 
    error, 
    isExpired, 
    refresh 
  } = useLiveViewUrl(usecaseId, executionId, executionStatus === 'executing');

  const handleOpenViewer = () => {
    setShowViewer(true);
    setDcvError(null);
  };

  const handleCloseViewer = () => {
    setShowViewer(false);
    setDcvError(null);
  };

  const handleDcvError = (error: any) => {
    console.error('DCV Error:', error);
    setDcvError(error.message || 'Failed to connect to live session');
  };

  const isExecutionActive = executionStatus === 'executing';
  const hasLiveView = liveViewUrl && !isExpired;

  return (
    <>
      <Container
        header={
          <Header
            variant="h3"
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                <Button
                  iconName="refresh"
                  variant="icon"
                  onClick={refresh}
                  loading={isLoading}
                  ariaLabel="Refresh live view status"
                />
                {hasLiveView && (
                  <Button
                    variant="primary"
                    iconName="view-full"
                    onClick={handleOpenViewer}
                  >
                    View Live Session
                  </Button>
                )}
              </SpaceBetween>
            }
          >
            Live Browser View
          </Header>
        }
      >
        <SpaceBetween direction="vertical" size="m">
          {isLoading && (
            <Box textAlign="center" padding="l">
              <SpaceBetween direction="vertical" size="m" alignItems="center">
                <Spinner size="large" />
                <div>Checking for live session...</div>
              </SpaceBetween>
            </Box>
          )}

          {error && (
            <Alert type="error" dismissible onDismiss={() => {}}>
              {error}
            </Alert>
          )}

          {!isLoading && !error && !hasLiveView && isExecutionActive && (
            <Alert type="info">
              <SpaceBetween direction="vertical" size="xs">
                <div>Execution is running but no live view session is available yet.</div>
                <div>The live view will appear once the browser session starts.</div>
              </SpaceBetween>
            </Alert>
          )}

          {!isLoading && !error && !hasLiveView && !isExecutionActive && (
            <Alert type="info">
              No live view session available. Live view is only available during active executions.
            </Alert>
          )}

          {isExpired && (
            <Alert type="warning">
              The live view session has expired. Live sessions are available for 24 hours after creation.
            </Alert>
          )}

          {dcvError && (
            <Alert type="error" dismissible onDismiss={() => setDcvError(null)}>
              <SpaceBetween direction="vertical" size="xs">
                <div><strong>Connection Error:</strong> {dcvError}</div>
                <div>You can try opening the session in a new tab using the link above.</div>
              </SpaceBetween>
            </Alert>
          )}
        </SpaceBetween>
      </Container>

      {/* DCV Viewer Modal */}
      <Modal
        onDismiss={handleCloseViewer}
        visible={showViewer}
        closeAriaLabel="Close live view"
        size="max"
        header="Live Browser Session"
      >
        {hasLiveView && (
          <RemoteBrowser
            presignedUrl={liveViewUrl}
            // width={1400}
            // height={900}
            // onConnect={() => console.log('DCV connected')}
            // onDisconnect={() => console.log('DCV disconnected')}
            // onError={handleDcvError}
          />
        )}
      </Modal>
    </>
  );
}