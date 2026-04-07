import { useState, useEffect, useCallback, useRef } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Spinner from "@cloudscape-design/components/spinner";
import Alert from "@cloudscape-design/components/alert";
import Box from "@cloudscape-design/components/box";
import Button from "@cloudscape-design/components/button";
import { RemoteBrowser } from '../dcv/DCVViewer';
import { useLiveViewUrl } from '../../hooks/useLiveViewUrl';
import { wizardApi, RecordingData } from '../../utils/api';
import RecordingControls, { RecordingStatus } from './RecordingControls';

export interface BrowserSessionPanelProps {
    sessionId: string;
    usecaseId: string;
    onSessionEnd: () => void;
    onRecordingComplete: (data: RecordingData) => void;
}

const RECORDING_POLL_INTERVAL_MS = 2000;
const RECORDING_POLL_TIMEOUT_MS = 60000;

const isMac = typeof navigator !== 'undefined' && /Mac/.test(navigator.platform);

export default function BrowserSessionPanel({
    sessionId,
    usecaseId,
    onSessionEnd,
    onRecordingComplete,
}: BrowserSessionPanelProps) {
    const [recordingStatus, setRecordingStatus] = useState<RecordingStatus>('idle');
    const [recordingError, setRecordingError] = useState<string | null>(null);
    const [sessionError, setSessionError] = useState<string | null>(null);

    const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const pollingStartRef = useRef<number>(0);

    const {
        liveViewUrl,
        error: liveViewError,
        isExpired,
    } = useLiveViewUrl(usecaseId, sessionId, true);

    const hasLiveView = !!liveViewUrl && !isExpired;
    const isWaitingForLiveView = !hasLiveView && !isExpired;
    const hasRealError = liveViewError && !liveViewError.includes('404') && !liveViewError.includes('not found');

    const stopPolling = useCallback(() => {
        if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
        }
    }, []);

    // Cleanup polling on unmount
    useEffect(() => {
        return () => stopPolling();
    }, [stopPolling]);

    const pollRecordingData = useCallback(() => {
        pollingStartRef.current = Date.now();

        pollingRef.current = setInterval(async () => {
            const elapsed = Date.now() - pollingStartRef.current;
            if (elapsed > RECORDING_POLL_TIMEOUT_MS) {
                stopPolling();
                setRecordingStatus('error');
                setRecordingError('Timed out waiting for recording data. Please try again.');
                return;
            }

            try {
                const response = await wizardApi.getRecordingData(sessionId, usecaseId);
                if (response.status === 'available' && response.recording_data) {
                    stopPolling();
                    setRecordingStatus('completed');
                    onRecordingComplete(response.recording_data);
                } else if (response.status === 'error') {
                    stopPolling();
                    setRecordingStatus('error');
                    setRecordingError(response.error || 'Recording failed on the worker. Please try again.');
                }
            } catch (err: any) {
                console.error('Error polling recording data:', err);
                // Don't stop polling on transient errors — only on timeout
            }
        }, RECORDING_POLL_INTERVAL_MS);
    }, [sessionId, usecaseId, onRecordingComplete, stopPolling]);

    const handleStartRecording = useCallback(async () => {
        setRecordingStatus('starting');
        setRecordingError(null);

        try {
            await wizardApi.sendRecordingCommand(sessionId, 'recording_start');
            setRecordingStatus('recording');
        } catch (err: any) {
            console.error('Failed to start recording:', err);
            setRecordingStatus('error');
            setRecordingError(err.message || 'Failed to start recording. Please try again.');
        }
    }, [sessionId]);

    const handleStopRecording = useCallback(async () => {
        setRecordingStatus('stopping');
        setRecordingError(null);

        try {
            await wizardApi.sendRecordingCommand(sessionId, 'recording_stop');
            // Start polling for recording data
            pollRecordingData();
        } catch (err: any) {
            console.error('Failed to stop recording:', err);
            setRecordingStatus('error');
            setRecordingError(err.message || 'Failed to stop recording. Please try again.');
        }
    }, [sessionId, pollRecordingData]);

    // Show error if live view fails after initial loading
    useEffect(() => {
        if (hasRealError) {
            setSessionError(liveViewError);
        }
    }, [hasRealError, liveViewError]);

    return (
        <Container
            header={
                <Header
                    variant="h2"
                    actions={
                        <Button
                            variant="normal"
                            iconName="close"
                            onClick={onSessionEnd}
                        >
                            End Session
                        </Button>
                    }
                >
                    Browser Session
                </Header>
            }
        >
            <SpaceBetween direction="vertical" size="m">
                {/* Session-level error */}
                {sessionError && (
                    <Alert
                        type="error"
                        dismissible
                        onDismiss={() => setSessionError(null)}
                    >
                        {sessionError}
                    </Alert>
                )}

                {/* Expired session warning */}
                {isExpired && (
                    <Alert type="warning">
                        Live view session has expired. The browser session may have timed out.
                    </Alert>
                )}

                {/* Loading state while waiting for live view URL */}
                {isWaitingForLiveView && !sessionError && (
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

                {/* DCV Viewer with minimum 500px height per requirement 8.3 */}
                {hasLiveView && (
                    <>
                        <div
                            data-testid="dcv-viewer-container"
                            style={{
                                width: '100%',
                                minHeight: '500px',
                                height: '600px',
                                border: '1px solid var(--color-border-divider-default)',
                                borderRadius: '8px',
                                overflow: 'hidden',
                                position: 'relative',
                                backgroundColor: '#000',
                            }}
                        >
                            <div style={{
                                width: '100%',
                                height: '100%',
                                position: 'absolute',
                                top: 0,
                                left: 0,
                            }}>
                                <RemoteBrowser presignedUrl={liveViewUrl} />
                            </div>
                        </div>

                        {/* macOS keyboard hint — the remote session runs Linux where Ctrl is the modifier key */}
                        {isMac && (
                            <Box variant="small" color="text-body-secondary" padding={{ top: 'xs' }}>
                                Tip: Use Ctrl instead of ⌘ for keyboard shortcuts (e.g. Ctrl+C, Ctrl+V) in the remote browser.
                            </Box>
                        )}

                        {/* Recording controls positioned within the browser session panel per requirement 8.4 */}
                        <Box padding={{ top: 'm' }}>
                            <RecordingControls
                                sessionId={sessionId}
                                recordingStatus={recordingStatus}
                                onStartRecording={handleStartRecording}
                                onStopRecording={handleStopRecording}
                                error={recordingError}
                            />
                        </Box>
                    </>
                )}
            </SpaceBetween>
        </Container>
    );
}
