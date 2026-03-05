import { useState } from 'react';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import Box from '@cloudscape-design/components/box';
import Button from '@cloudscape-design/components/button';
import SpaceBetween from '@cloudscape-design/components/space-between';
import CopyToClipboard from '@cloudscape-design/components/copy-to-clipboard';
import StepHeader from './StepHeader';
import StepTraceContent, { TraceStep } from './StepTraceContent';
import { api } from '../../utils/api';

export interface StepExpandableSectionProps {
  step: any;
  expanded: boolean;
  onExpandChange: (expanded: boolean) => void;
  usecaseId: string;
  executionId: string;
}

export default function StepExpandableSection({
  step,
  expanded,
  onExpandChange,
  usecaseId,
  executionId,
}: StepExpandableSectionProps) {
  const [traceData, setTraceData] = useState<TraceStep[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const actId = step.actId || step.act_id;
  const hasTrace = actId && actId !== 'cached' && actId !== 'error';

  const handleToggle = async () => {
    const willExpand = !expanded;
    onExpandChange(willExpand);

    if (willExpand && !traceData) {
      setLoading(true);
      setError(null);
      try {
        const data = await api.get(
          `usecase/${usecaseId}/executions/${executionId}/steps/${step.sort}/trace`
        );
        setTraceData(data.trace_steps || []);
      } catch (err: any) {
        setError(err?.message || 'Failed to load trace data');
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <Container
      header={
        <Header
          actions={
            hasTrace ? (
              <Button
                variant="inline-link"
                iconName={expanded ? 'angle-up' : 'angle-down'}
                iconAlign="right"
                onClick={handleToggle}
              >
                {expanded ? 'Collapse' : 'Expand'}
              </Button>
            ) : undefined
          }
        >
          <StepHeader
            stepNum={step.sort}
            status={step.status || 'pending'}
            isCached={actId === 'cached'}
            instruction={step.instruction}
            stepType={step.step_type}
            validation={
              step.actual_value
                ? {
                    validation_type: step.validation_type,
                    validation_operator: step.validation_operator,
                    validation_value: step.validation_value,
                    actual_value: step.actual_value,
                  }
                : undefined
            }
            logs={step.logs}
          />
        </Header>
      }
    >
      {expanded && hasTrace && (
        <SpaceBetween size="s">
          <StepTraceContent
            traceSteps={traceData || []}
            loading={loading}
            error={error}
          />
          <Box fontSize="body-s" color="text-body-secondary">
            <CopyToClipboard
              copyButtonAriaLabel="Copy Act ID"
              copyErrorText="failed to copy"
              copySuccessText="copied"
              textToCopy={actId}
              variant="inline"
            />
          </Box>
        </SpaceBetween>
      )}
    </Container>
  );
}
