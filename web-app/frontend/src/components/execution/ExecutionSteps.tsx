import { useState } from 'react';
import Header from '@cloudscape-design/components/header';
import Button from '@cloudscape-design/components/button';
import SpaceBetween from '@cloudscape-design/components/space-between';
import StepExpandableSection from './StepExpandableSection';

interface ExecutionStepsProps {
  executionSteps: any[];
  usecaseId: string;
  executionId: string;
}

export default function ExecutionSteps({
  executionSteps,
  usecaseId,
  executionId,
}: ExecutionStepsProps) {
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());

  const handleExpandAll = () => {
    setExpandedSteps(new Set(executionSteps.map((step) => step.sort)));
  };

  const handleCollapseAll = () => {
    setExpandedSteps(new Set());
  };

  const handleStepExpandChange = (stepSort: number, expanded: boolean) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (expanded) {
        next.add(stepSort);
      } else {
        next.delete(stepSort);
      }
      return next;
    });
  };

  return (
    <SpaceBetween size="s">
      <Header
        variant="h2"
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            <Button onClick={handleExpandAll}>Expand All</Button>
            <Button onClick={handleCollapseAll}>Collapse All</Button>
          </SpaceBetween>
        }
      >
        Test Journey Steps
      </Header>
      {executionSteps.map((step) => (
        <StepExpandableSection
          key={step.sort}
          step={step}
          expanded={expandedSteps.has(step.sort)}
          onExpandChange={(expanded) => handleStepExpandChange(step.sort, expanded)}
          usecaseId={usecaseId}
          executionId={executionId}
        />
      ))}
    </SpaceBetween>
  );
}
