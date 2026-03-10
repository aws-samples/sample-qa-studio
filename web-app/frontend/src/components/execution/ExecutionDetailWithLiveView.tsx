import React from 'react';
import SpaceBetween from "@cloudscape-design/components/space-between";
import ColumnLayout from "@cloudscape-design/components/column-layout";
import LiveViewPanel from './LiveViewPanel';
import ExecutionSteps from './ExecutionSteps';

interface ExecutionDetailWithLiveViewProps {
  usecaseId: string;
  executionId: string;
  execution: any;
  executionSteps: any[];
}

// Helper function to get the current executing step or the last completed step
function getCurrentStep(steps: any[]) {
  if (!steps || steps.length === 0) return null;
  
  // First, try to find a step that's currently executing
  const executingStep = steps.find(step => step.status === 'executing');
  if (executingStep) {
    return {
      sort: executingStep.sort,
      instruction: executingStep.instruction,
      status: executingStep.status
    };
  }
  
  // If no executing step, find the last completed step
  const completedSteps = steps.filter(step => 
    step.status === 'success' || step.status === 'completed'
  );
  
  if (completedSteps.length > 0) {
    const lastCompleted = completedSteps[completedSteps.length - 1];
    return {
      sort: lastCompleted.sort,
      instruction: lastCompleted.instruction,
      status: lastCompleted.status
    };
  }
  
  // If no completed steps, return the first pending step
  const pendingStep = steps.find(step => step.status === 'pending');
  if (pendingStep) {
    return {
      sort: pendingStep.sort,
      instruction: pendingStep.instruction,
      status: pendingStep.status
    };
  }
  
  return null;
}

export default function ExecutionDetailWithLiveView({
  usecaseId,
  executionId,
  execution,
  executionSteps,
}: ExecutionDetailWithLiveViewProps) {
  return (
    <SpaceBetween direction="vertical" size="l">
      {/* Live View Panel - Show for executing or recently completed executions */}
      {(execution?.status === 'executing' || execution?.status === 'success' || execution?.status === 'error') && (
        <LiveViewPanel
          usecaseId={usecaseId}
          executionId={executionId}
          executionStatus={execution?.status}
          currentStep={getCurrentStep(executionSteps)}
        />
      )}

      {/* Two-column layout for larger screens */}
      <ColumnLayout columns={1} variant="text-grid">
        <ExecutionSteps
          executionSteps={executionSteps}
          usecaseId={usecaseId}
          executionId={executionId}
        />
      </ColumnLayout>
    </SpaceBetween>
  );
}