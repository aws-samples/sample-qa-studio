import React from 'react';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Badge from '@cloudscape-design/components/badge';
import Box from '@cloudscape-design/components/box';
import StatusIndicatorCompact from '../common/StatusIndicatorCompact';
import ValidationResult from '../common/ValidationResult';

export interface StepHeaderProps {
  stepNum: number;
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
  stepNum,
  status,
  isCached,
  instruction,
  stepType,
  validation,
  logs,
}: StepHeaderProps) {
  return (
    <SpaceBetween direction="horizontal" size="xs" alignItems="center">
      <Box fontWeight="bold" display="inline">
        Step {stepNum}
      </Box>

      <StatusIndicatorCompact status={status as any} />

      {isCached && <Badge color="blue">Cached</Badge>}

      <Box display="inline" color="text-body-secondary">
        {instruction}
      </Box>

      {(stepType === 'validation' || stepType === 'assertion') && validation && (
        <ValidationResult
          validationType={validation.validation_type}
          validationOperator={validation.validation_operator}
          validationValue={validation.validation_value}
          actualValue={validation.actual_value}
          status={status}
        />
      )}

      {stepType === 'download' && validation?.actual_value && (
        <Box display="inline" fontSize="body-s" color="text-body-secondary">
          Downloaded: {validation.actual_value}
        </Box>
      )}

      {logs && (
        <Box display="inline">
          <pre style={{ margin: 0, fontSize: '12px' }}>{logs}</pre>
        </Box>
      )}
    </SpaceBetween>
  );
}
