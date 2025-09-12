import React from 'react';
import Alert from "@cloudscape-design/components/alert";
import Box from "@cloudscape-design/components/box";
import SpaceBetween from "@cloudscape-design/components/space-between";

interface FormValidationSummaryProps {
  errors: Record<string, string>;
  warnings: Record<string, string>;
  isFormValid: boolean;
  showSuccessMessage?: boolean;
}

export default function FormValidationSummary({
  errors,
  warnings,
  isFormValid,
  showSuccessMessage = false
}: FormValidationSummaryProps) {
  const errorCount = Object.keys(errors).filter(key => errors[key]).length;
  const warningCount = Object.keys(warnings).filter(key => warnings[key]).length;

  // Don't show anything if form is valid and no warnings
  if (isFormValid && warningCount === 0 && !showSuccessMessage) {
    return null;
  }

  // Show success message when form is valid
  if (isFormValid && showSuccessMessage) {
    return (
      <Alert type="success" header="Form is ready">
        All required fields are completed and valid. You can now generate your use case.
      </Alert>
    );
  }

  // Show errors
  if (errorCount > 0) {
    const errorList = Object.entries(errors)
      .filter(([_, error]) => error)
      .map(([field, error]) => ({ field, error }));

    return (
      <Alert 
        type="error" 
        header={`Please fix ${errorCount} error${errorCount > 1 ? 's' : ''} before continuing`}
      >
        <SpaceBetween direction="vertical" size="xs">
          {errorList.map(({ field, error }, index) => (
            <Box key={index} variant="small">
              <strong>{field.charAt(0).toUpperCase() + field.slice(1)}:</strong> {error}
            </Box>
          ))}
        </SpaceBetween>
      </Alert>
    );
  }

  // Show warnings only
  if (warningCount > 0) {
    const warningList = Object.entries(warnings)
      .filter(([_, warning]) => warning)
      .map(([field, warning]) => ({ field, warning }));

    return (
      <Alert 
        type="warning" 
        header={`${warningCount} suggestion${warningCount > 1 ? 's' : ''} to improve your input`}
      >
        <SpaceBetween direction="vertical" size="xs">
          {warningList.map(({ field, warning }, index) => (
            <Box key={index} variant="small">
              <strong>{field.charAt(0).toUpperCase() + field.slice(1)}:</strong> {warning}
            </Box>
          ))}
          <Box variant="small" color="text-body-secondary">
            These are suggestions and won't prevent form submission.
          </Box>
        </SpaceBetween>
      </Alert>
    );
  }

  return null;
}