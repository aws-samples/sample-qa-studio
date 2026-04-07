import SpaceBetween from "@cloudscape-design/components/space-between";
import StatusIndicator from "@cloudscape-design/components/status-indicator";
import Box from "@cloudscape-design/components/box";
import { RecordingData } from "../../utils/api";

export interface RecordingSummaryProps {
    recordingData: RecordingData;
}

function formatDuration(startedAt: number, stoppedAt?: number): string {
    if (!stoppedAt) return "In progress";
    const totalSeconds = Math.round((stoppedAt - startedAt) / 1000);
    if (totalSeconds < 0) return "0s";
    if (totalSeconds < 60) return `${totalSeconds}s`;
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`;
}

export default function RecordingSummary({ recordingData }: RecordingSummaryProps) {
    const { session } = recordingData.data;
    const eventCount = recordingData.data.event_count;
    const duration = formatDuration(session.startedAt, session.stoppedAt);

    return (
        <Box padding={{ vertical: "xs" }}>
            <SpaceBetween direction="horizontal" size="m" alignItems="center">
                <StatusIndicator type="success">Recording available</StatusIndicator>
                <Box color="text-body-secondary" fontSize="body-s">
                    {eventCount} {eventCount === 1 ? "event" : "events"} · {duration}
                </Box>
            </SpaceBetween>
        </Box>
    );
}
