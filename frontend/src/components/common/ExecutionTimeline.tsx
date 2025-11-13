import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import Box from "@cloudscape-design/components/box";
import Steps from "@cloudscape-design/components/steps";
import SpaceBetween from "@cloudscape-design/components/space-between";

interface ExecutionTimelineProps {
  execution: {
    createdAt?: string;
    created_at?: string;
    executingAt?: string;
    executing_at?: string;
    completedAt?: string;
    completed_at?: string;
    status: string;
  };
}

export default function ExecutionTimeline({ execution }: ExecutionTimelineProps) {
  // Helper function to calculate duration between two timestamps
  const calculateDuration = (start: string, end: string): string => {

    try {
      const startTime = new Date(start).getTime();
      const endTime = new Date(end).getTime();
      const diffMs = endTime - startTime;

      if (isNaN(diffMs) || diffMs < 0) return 'Invalid';

      if (diffMs < 1000) {
        return `${diffMs}ms`;
      } else if (diffMs < 60000) {
        return `${Math.round(diffMs / 1000)}s`;
      } else if (diffMs < 3600000) {
        const minutes = Math.floor(diffMs / 60000);
        const seconds = Math.round((diffMs % 60000) / 1000);
        return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`;
      } else {
        const hours = Math.floor(diffMs / 3600000);
        const minutes = Math.round((diffMs % 3600000) / 60000);
        return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
      }
    } catch {
      return 'Unknown';
    }
  };

  // Get timestamps with fallback to different field names
  const createdAt = execution.createdAt || execution.created_at;
  const executingAt = execution.executingAt || execution.executing_at;
  const completedAt = execution.completedAt || execution.completed_at;

  // Build steps data for Cloudscape Steps component
  const steps = [];
  let activeStepIndex = 0;

  // Step 1: Created
  if (createdAt) {
    steps.push({
      header: 'Created',
      info: new Date(createdAt).toLocaleString(),
      description: 'Execution request created and queued',
      status: 'success' as const
    });
  }

  // Step 2: Started Executing
  if (executingAt && createdAt) {
    const queueTime = calculateDuration(createdAt, executingAt);
    steps.push({
      header: 'Started Executing',
      info: new Date(executingAt).toLocaleString(),
      description: `Execution began processing after ${queueTime} in queue`,
      status: 'success' as const
    });
  } else if (createdAt && !executingAt && execution.status === 'pending') {
    const waitTime = calculateDuration(createdAt, new Date().toISOString());
    steps.push({
      header: 'Waiting in Queue',
      info: `Waiting for ${waitTime}`,
      description: 'Waiting to start execution',
      status: 'pending' as const
    });
    activeStepIndex = 1;
  }

  // Step 3: Completion
  if (completedAt) {
    const isSuccess = execution.status === 'success';
    const executionTime = executingAt
      ? calculateDuration(executingAt, completedAt)
      : calculateDuration(createdAt!, completedAt);

    steps.push({
      header: isSuccess ? 'Completed Successfully' : 'Failed',
      info: new Date(completedAt).toLocaleString(),
      description: isSuccess
        ? `Execution completed successfully after ${executionTime}`
        : `Execution failed after ${executionTime}`,
      status: isSuccess ? 'success' as const : 'error' as const
    });
  } else if (execution.status === 'executing' || execution.status === 'in-progress') {
    const currentTime = executingAt
      ? calculateDuration(executingAt, new Date().toISOString())
      : calculateDuration(createdAt!, new Date().toISOString());

    steps.push({
      header: 'Currently Executing',
      info: `Running for ${currentTime}`,
      description: 'Execution in progress',
      status: 'in-progress' as const
    });
    activeStepIndex = steps.length - 1;
  } else if (!completedAt && executingAt) {
    // Execution started but not completed yet
    steps.push({
      header: 'Completion',
      description: 'Waiting for execution to complete',
      status: 'pending' as const
    });
    activeStepIndex = steps.length - 1;
  }

  // Calculate summary metrics
  const totalDuration = completedAt && createdAt ? calculateDuration(createdAt, completedAt) : null;
  const queueDuration = executingAt && createdAt ? calculateDuration(createdAt, executingAt) : null;
  const executionDuration = completedAt && executingAt ? calculateDuration(executingAt, completedAt) : null;

  if (steps.length === 0) {
    return (
      <Container header={<Header variant="h2">Execution Timeline</Header>}>
        <Box textAlign="center" padding="l">
          <Box variant="strong">No timeline data available</Box>
          <Box variant="p" color="text-body-secondary">
            Timeline information will appear here once the execution has timestamp data.
          </Box>
        </Box>
      </Container>
    );
  }

  return (
    <Container header={<Header variant="h2">Execution Timeline</Header>}>
      <SpaceBetween direction="vertical" size="l">
        {/* Cloudscape Steps Component */}
        <Steps steps={steps} />

        {/* Compact Summary */}
        {(totalDuration || queueDuration || executionDuration) && (
          <Box>
            <Box variant="h4">Summary</Box>
            <SpaceBetween direction="vertical" size="xs">
              {totalDuration && (
                <Box>
                  <Box variant="small" color="text-body-secondary">Total Duration</Box>
                  <Box variant="strong" color="text-status-info"> {totalDuration}</Box>
                </Box>
              )}
              {queueDuration && (
                <Box>
                  <Box variant="small" color="text-body-secondary">Queue Time</Box>
                  <Box variant="strong"> {queueDuration}</Box>
                </Box>
              )}
              {executionDuration && (
                <Box>
                  <Box variant="small" color="text-body-secondary">Execution Time</Box>
                  <Box variant="strong"> {executionDuration}</Box>
                </Box>
              )}
            </SpaceBetween>
          </Box>
        )}
      </SpaceBetween>
    </Container>
  );
}