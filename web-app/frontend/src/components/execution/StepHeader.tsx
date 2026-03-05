import SpaceBetween from '@cloudscape-design/components/space-between';
import Badge from '@cloudscape-design/components/badge';
import Box from '@cloudscape-design/components/box';
import StatusIndicatorCompact from '../common/StatusIndicatorCompact';
import ValidationResult from '../common/ValidationResult';

export interface StepHeaderProps {
  status: string;
  isCached: boolean;
  instruction: string;
  stepType: string;
  validation?: {
    validation_type: string;
    validation_operator: string;
    validation_value: string;
    actual_value: string;
  };
  logs?: string;
}

export default function StepHeader({
  status,
  isCached,
  instruction,
  stepType,
  validation,
  logs,
}: StepHeaderProps) {
  const hasValidation = (stepType === 'validation' || stepType === 'assertion') && validation;
  const hasDownload = stepType === 'download' && validation?.actual_value;

  return (
    <SpaceBetween direction="vertical" size="xxs">
      {/* Top row: status icon + step number + instruction */}
      <SpaceBetween direction="horizontal" size="xs" alignItems="center">
        <StatusIndicatorCompact status={status as any} />

        <Box display="inline" color="text-body-secondary">
          {instruction}
        </Box>

        {isCached && <Badge color="blue">Cached</Badge>}
      </SpaceBetween>

      {/* Validation info below */}
      {hasValidation && (
        <Box padding={{ left: 'l' }}>
          <ValidationResult
            validationType={validation.validation_type}
            validationOperator={validation.validation_operator}
            validationValue={validation.validation_value}
            actualValue={validation.actual_value}
            status={status}
          />
        </Box>
      )}

      {hasDownload && (
        <Box padding={{ left: 'l' }} fontSize="body-s" color="text-body-secondary">
          Downloaded: {validation.actual_value}
        </Box>
      )}

      {logs && (
        <Box padding={{ left: 'l' }}>
          <pre style={{ margin: 0, fontSize: '12px' }}>{logs}</pre>
        </Box>
      )}
    </SpaceBetween>
  );
}
