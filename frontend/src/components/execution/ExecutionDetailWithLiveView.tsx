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
  onViewFile: (content: { url: string, title: string, fileType: string }) => void;
}

export default function ExecutionDetailWithLiveView({
  usecaseId,
  executionId,
  execution,
  executionSteps,
  onViewFile
}: ExecutionDetailWithLiveViewProps) {
  return (
    <SpaceBetween direction="vertical" size="l">
      {/* Live View Panel - Show for executing or recently completed executions */}
      {(execution?.status === 'executing' || execution?.status === 'success' || execution?.status === 'error') && (
        <LiveViewPanel
          usecaseId={usecaseId}
          executionId={executionId}
          executionStatus={execution?.status}
        />
      )}

      {/* Two-column layout for larger screens */}
      <ColumnLayout columns={1} variant="text-grid">
        <ExecutionSteps
          executionSteps={executionSteps}
          usecaseId={usecaseId}
          executionId={executionId}
          onViewFile={onViewFile}
        />
      </ColumnLayout>
    </SpaceBetween>
  );
}