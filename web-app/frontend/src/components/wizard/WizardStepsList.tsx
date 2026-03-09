import ExecutionSteps from '../execution/ExecutionSteps';

interface WizardStepsListProps {
  steps: any[];
  usecaseId: string;
  sessionId: string;
}

export default function WizardStepsList({ 
  steps,
  usecaseId,
  sessionId,
}: WizardStepsListProps) {
  return (
    <ExecutionSteps
      executionSteps={steps}
      usecaseId={usecaseId}
      executionId={sessionId}
    />
  );
}
