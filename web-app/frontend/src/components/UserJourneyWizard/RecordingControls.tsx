import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import StatusIndicator from "@cloudscape-design/components/status-indicator";
import Spinner from "@cloudscape-design/components/spinner";
import Alert from "@cloudscape-design/components/alert";
import Box from "@cloudscape-design/components/box";

export type RecordingStatus = 'idle' | 'starting' | 'recording' | 'stopping' | 'completed' | 'error';

export interface RecordingControlsProps {
    sessionId: string;
    recordingStatus: RecordingStatus;
    onStartRecording: () => void;
    onStopRecording: () => void;
    error: string | null;
}

export default function RecordingControls({
    sessionId,
    recordingStatus,
    onStartRecording,
    onStopRecording,
    error,
}: RecordingControlsProps) {
    const showStartButton = recordingStatus === 'idle' || recordingStatus === 'completed';
    const showStopButton = recordingStatus === 'recording';
    const isTransitioning = recordingStatus === 'starting' || recordingStatus === 'stopping';
    const isError = recordingStatus === 'error';

    return (
        <SpaceBetween direction="vertical" size="s">
            {isTransitioning && (
                <Box textAlign="center" padding="s">
                    <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                        <Spinner />
                        <span>{recordingStatus === 'starting' ? 'Starting recording...' : 'Stopping recording...'}</span>
                    </SpaceBetween>
                </Box>
            )}

            {showStartButton && (
                <Button
                    iconName="caret-right-filled"
                    onClick={onStartRecording}
                >
                    Start Recording
                </Button>
            )}

            {showStopButton && (
                <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                    <StatusIndicator type="in-progress">Recording</StatusIndicator>
                    <Button
                        variant="normal"
                        iconName="close"
                        onClick={onStopRecording}
                    >
                        Stop Recording
                    </Button>
                </SpaceBetween>
            )}

            {isError && error && (
                <Alert
                    type="error"
                    action={
                        <Button onClick={onStartRecording}>
                            Retry
                        </Button>
                    }
                >
                    {error}
                </Alert>
            )}
        </SpaceBetween>
    );
}
