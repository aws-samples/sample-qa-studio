import React from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import Box from "@cloudscape-design/components/box";
import StatusIndicator from "@cloudscape-design/components/status-indicator";
import SpaceBetween from "@cloudscape-design/components/space-between";
// Removed unused KeyValuePairs import

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

  // Build timeline data
  const timelineSteps = [];

  if (createdAt) {
    timelineSteps.push({
      label: 'Created',
      timestamp: new Date(createdAt).toLocaleString(),
      status: 'success' as const,
      description: 'Execution request created and queued',
      phase: 'creation'
    });
  }

  if (executingAt && createdAt) {
    const queueTime = calculateDuration(createdAt, executingAt);
    timelineSteps.push({
      label: 'Started Executing',
      timestamp: new Date(executingAt).toLocaleString(),
      status: 'success' as const,
      description: `Execution began processing after ${queueTime} in queue`,
      transitionTime: queueTime,
      phase: 'execution-start'
    });
  }

  if (completedAt) {
    const isSuccess = execution.status === 'success';
    const executionTime = executingAt
      ? calculateDuration(executingAt, completedAt)
      : calculateDuration(createdAt!, completedAt);

    timelineSteps.push({
      label: isSuccess ? 'Completed Successfully' : 'Failed',
      timestamp: new Date(completedAt).toLocaleString(),
      status: isSuccess ? 'success' as const : 'error' as const,
      description: isSuccess
        ? `Execution completed successfully after ${executionTime}`
        : `Execution failed after ${executionTime}`,
      transitionTime: executionTime,
      phase: 'completion'
    });
  } else if (execution.status === 'executing' || execution.status === 'in-progress') {
    const currentTime = executingAt
      ? calculateDuration(executingAt, new Date().toISOString())
      : calculateDuration(createdAt!, new Date().toISOString());

    timelineSteps.push({
      label: 'Currently Executing',
      timestamp: 'In progress',
      status: 'in-progress' as const,
      description: `Execution has been running for ${currentTime}`,
      transitionTime: currentTime,
      phase: 'in-progress'
    });
  } else if (createdAt && !executingAt && execution.status === 'pending') {
    const waitTime = calculateDuration(createdAt, new Date().toISOString());
    timelineSteps.push({
      label: 'Waiting in Queue',
      timestamp: 'Pending',
      status: 'pending' as const,
      description: `Waiting to start execution for ${waitTime}`,
      transitionTime: waitTime,
      phase: 'queued'
    });
  }

  // Calculate summary metrics
  const totalDuration = completedAt && createdAt ? calculateDuration(createdAt, completedAt) : null;
  const queueDuration = executingAt && createdAt ? calculateDuration(createdAt, executingAt) : null;
  const executionDuration = completedAt && executingAt ? calculateDuration(executingAt, completedAt) : null;

  if (timelineSteps.length === 0) {
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

      {/* Timeline Steps */}
      <SpaceBetween direction="vertical" size="s">
        {timelineSteps.map((step, index) => (
          <Box key={index}>
            <SpaceBetween direction="vertical" size="xs">
              <StatusIndicator type={step.status}>
                <Box variant="strong" fontSize="body-s">{step.label}</Box>
              </StatusIndicator>

              <Box margin={{ left: 'l' }}>
                <Box variant="small" color="text-body-secondary">
                    &nbsp;{step.timestamp}
                </Box>
                {step.transitionTime && (
                  <Box variant="strong" color="text-status-info" fontSize="body-s">
                    &nbsp;{step.transitionTime}
                  </Box>
                )}
              </Box>
            </SpaceBetween>
          </Box>
        ))}
      </SpaceBetween>

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
    </Container>
  );
}