import ExecutionSteps from '../execution/ExecutionSteps';

interface WizardStepsListProps {
  steps: any[];
  usecaseId: string;
  sessionId: string;
  onViewFile: (content: { url: string, title: string, fileType: string }) => void;
}

export default function WizardStepsList({ 
  steps,
  usecaseId,
  sessionId,
  onViewFile
}: WizardStepsListProps) {
  return (
    <ExecutionSteps
      executionSteps={steps}
      usecaseId={usecaseId}
      executionId={sessionId}
      onViewFile={onViewFile}
    />
  );
}
