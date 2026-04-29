import { useState, useEffect } from 'react';
import SpaceBetween from "@cloudscape-design/components/space-between";
import FormField from "@cloudscape-design/components/form-field";
import Select from "@cloudscape-design/components/select";
import Textarea from "@cloudscape-design/components/textarea";
import Input from "@cloudscape-design/components/input";
import { api } from '../../utils/api';

interface StepFormProps {
  usecaseId: string;
  stepType: string;
  instruction: string;
  selectedSecret: string;
  validationType: string;
  validationOperator: string;
  validationValue: string;
  captureVariable: string;
  valueType: string;
  assertionVariable: string;
  booleanInputMode: string;
  existingSteps?: any[];
  disabled?: boolean;
  onStepTypeChange: (value: string) => void;
  onInstructionChange: (value: string) => void;
  onSelectedSecretChange: (value: string) => void;
  onValidationTypeChange: (value: string) => void;
  onValidationOperatorChange: (value: string) => void;
  onValidationValueChange: (value: string) => void;
  onCaptureVariableChange: (value: string) => void;
  onValueTypeChange: (value: string) => void;
  onAssertionVariableChange: (value: string) => void;
  onBooleanInputModeChange: (value: string) => void;
}

const STEP_TYPE_OPTIONS = [
  { label: 'Navigation', value: 'navigation' },
  { label: 'Browser', value: 'browser' },
  { label: 'Transform', value: 'transform' },
  { label: 'Secret', value: 'secret' },
  { label: 'Validation', value: 'validation' },
  { label: 'Retrieve Value', value: 'retrieve_value' },
  { label: 'Assertion', value: 'assertion' },
  { label: 'Download', value: 'download' }
];

const VALIDATION_TYPE_OPTIONS = [
  { label: 'Boolean (True/False)', value: 'bool' },
  { label: 'String Comparison', value: 'string' },
  { label: 'Number Comparison', value: 'number' }
];

const VALUE_TYPE_OPTIONS = [
  { label: 'String', value: 'string' },
  { label: 'Number', value: 'number' },
  { label: 'Boolean', value: 'bool' }
];

const VALIDATION_OPERATOR_OPTIONS = {
  string: [
    { label: 'Exact Match', value: 'exact' },
    { label: 'Exact Match (Case Insensitive)', value: 'exact_case_insensitive' },
    { label: 'Not Equal', value: 'not_equal' },
    { label: 'Contains', value: 'contains' },
    { label: 'Contains (Case Insensitive)', value: 'contains_case_insensitive' }
  ],
  number: [
    { label: 'Equals', value: 'equals' },
    { label: 'Less Than', value: 'less_then' },
    { label: 'Greater Than', value: 'greater_then' },
    { label: 'Greater or Equal Than', value: 'greater_or_equal_then' },
    { label: 'Less or Equal Than', value: 'less_or_equal_then' }
  ]
};

const BOOLEAN_OPTIONS = [
  { label: 'True', value: 'true' },
  { label: 'False', value: 'false' },
  { label: 'Use Variable', value: 'variable' }
];

export default function StepForm({
  usecaseId,
  stepType,
  instruction,
  selectedSecret,
  validationType,
  validationOperator,
  validationValue,
  captureVariable,
  valueType,
  assertionVariable,
  booleanInputMode,
  existingSteps = [],
  disabled = false,
  onStepTypeChange,
  onInstructionChange,
  onSelectedSecretChange,
  onValidationTypeChange,
  onValidationOperatorChange,
  onValidationValueChange,
  onCaptureVariableChange,
  onValueTypeChange,
  onAssertionVariableChange,
  onBooleanInputModeChange
}: StepFormProps) {
  const [availableSecrets, setAvailableSecrets] = useState<any[]>([]);

  // Load available secrets when step type changes to secret
  useEffect(() => {
    if (stepType === 'secret') {
      loadSecrets();
    }
  }, [stepType, usecaseId]);

  const loadSecrets = async () => {
    try {
      const response = await api.get(`usecase/${usecaseId}/secrets`);
      setAvailableSecrets(response.secrets || []);
    } catch (error) {
      console.error('Failed to load secrets:', error);
      setAvailableSecrets([]);
    }
  };

  return (
    <SpaceBetween direction="vertical" size="m">
      <FormField label="Step Type">
        <Select
          selectedOption={STEP_TYPE_OPTIONS.find(opt => opt.value === stepType) || null}
          onChange={({ detail }) => onStepTypeChange(detail.selectedOption.value || 'navigation')}
          options={STEP_TYPE_OPTIONS}
          disabled={disabled}
        />
      </FormField>

      {stepType !== 'assertion' && (
        <FormField
          label="Instruction"
          description={
            stepType === 'navigation' ? 'Describe the action to perform on the page' :
            stepType === 'url' ? 'Enter the URL to navigate to (e.g., "https://example.com/login")' :
            stepType === 'secret' ? 'Describe the action (e.g., "Type password in login field")' :
            stepType === 'validation' ? 'Describe what should be validated on the page' :
            stepType === 'download' ? 'Describe the action that triggers the download. Automatically handles downloads in popups or current page.' :
            'Describe what value to retrieve from the page'
          }
        >
          <Textarea
            value={instruction}
            onChange={({ detail }) => onInstructionChange(detail.value)}
            placeholder={
              stepType === 'navigation' ? 'Enter navigation instruction' :
              stepType === 'url' ? 'https://example.com/page' :
              stepType === 'secret' ? 'Describe the action with the secret' :
              stepType === 'validation' ? 'Describe the validation to perform' :
              stepType === 'download' ? 'Click the download button' :
              'Describe what to retrieve (e.g., "Get the product price")'
            }
            rows={3}
            disabled={disabled}
          />
        </FormField>
      )}

      {stepType === 'secret' && (
        <FormField
          label="Select Secret"
          description="Choose which secret to use for this step"
        >
          <Select
            selectedOption={availableSecrets.find(secret => secret.key === selectedSecret) ?
              { label: availableSecrets.find(secret => secret.key === selectedSecret)?.key || '', value: selectedSecret } :
              null
            }
            onChange={({ detail }) => onSelectedSecretChange(detail.selectedOption?.value || '')}
            options={availableSecrets.map(secret => ({
              label: secret.key,
              value: secret.key,
              description: secret.description
            }))}
            placeholder="Select a secret"
            empty="No secrets available. Create secrets first."
            disabled={disabled}
          />
        </FormField>
      )}

      {stepType === 'validation' && (
        <>
          <FormField label="Validation Type">
            <Select
              selectedOption={VALIDATION_TYPE_OPTIONS.find(opt => opt.value === validationType) || null}
              onChange={({ detail }) => {
                const newType = detail.selectedOption?.value || 'bool';
                onValidationTypeChange(newType);
                // Reset operator to first available option for the new type
                if (newType === 'string') {
                  onValidationOperatorChange('exact');
                } else if (newType === 'number') {
                  onValidationOperatorChange('equals');
                }
              }}
              options={VALIDATION_TYPE_OPTIONS}
              disabled={disabled}
            />
          </FormField>

          {validationType === 'bool' && (
            <>
              <FormField
                label="Expected Boolean Value"
                description="Select true/false or use a variable"
              >
                <Select
                  selectedOption={BOOLEAN_OPTIONS.find(opt => opt.value === booleanInputMode) || null}
                  onChange={({ detail }) => {
                    const mode = detail.selectedOption?.value || 'true';
                    onBooleanInputModeChange(mode);
                    if (mode === 'true' || mode === 'false') {
                      onValidationValueChange(mode);
                    } else {
                      onValidationValueChange('');
                    }
                  }}
                  options={BOOLEAN_OPTIONS}
                  disabled={disabled}
                />
              </FormField>
              {booleanInputMode === 'variable' && (
                <FormField
                  label="Variable Expression"
                  description="Enter a variable that evaluates to a boolean (e.g., {{myBooleanVar}})"
                >
                  <Input
                    value={validationValue}
                    onChange={({ detail }) => onValidationValueChange(detail.value)}
                    placeholder="{{myBooleanVar}}"
                    disabled={disabled}
                  />
                </FormField>
              )}
            </>
          )}

          {(validationType === 'string' || validationType === 'number') && (
            <>
              <FormField label="Validation Operator">
                <Select
                  selectedOption={
                    VALIDATION_OPERATOR_OPTIONS[validationType as keyof typeof VALIDATION_OPERATOR_OPTIONS]
                      ?.find(opt => opt.value === validationOperator) || null
                  }
                  onChange={({ detail }) => onValidationOperatorChange(detail.selectedOption?.value ||
                    (validationType === 'string' ? 'exact' : 'equals'))}
                  options={VALIDATION_OPERATOR_OPTIONS[validationType as keyof typeof VALIDATION_OPERATOR_OPTIONS] || []}
                  disabled={disabled}
                />
              </FormField>

              <FormField
                label="Expected Value"
                description={
                  validationType === 'number'
                    ? 'Enter a numeric value. You can use variables like {{UniqueID}}, {{Time}}, {{ExecutionID}}, or custom variables.'
                    : 'Enter the expected text value. You can use variables like {{UniqueID}}, {{Time}}, {{ExecutionID}}, or custom variables.'
                }
              >
                <Input
                  value={validationValue}
                  onChange={({ detail }) => onValidationValueChange(detail.value)}
                  placeholder={
                    validationType === 'number'
                      ? 'Enter a number (e.g., 42, 3.14) or use variables like {{UniqueID}}'
                      : 'Enter expected value or use variables like {{UniqueID}}, {{Time}}'
                  }
                  type="text"
                  disabled={disabled}
                />
              </FormField>
            </>
          )}
        </>
      )}

      {stepType === 'retrieve_value' && (
        <>
          <FormField
            label="Variable Name"
            description="Name for the captured variable (will be available as {{variableName}} in subsequent steps)"
          >
            <Input
              value={captureVariable}
              onChange={({ detail }) => onCaptureVariableChange(detail.value)}
              placeholder="e.g., product_price, user_id, status"
              disabled={disabled}
            />
          </FormField>

          <FormField
            label="Value Type"
            description="Expected type of the retrieved value"
          >
            <Select
              selectedOption={VALUE_TYPE_OPTIONS.find(opt => opt.value === valueType) || null}
              onChange={({ detail }) => onValueTypeChange(detail.selectedOption?.value || 'string')}
              options={VALUE_TYPE_OPTIONS}
              disabled={disabled}
            />
          </FormField>
        </>
      )}

      {stepType === 'assertion' && (
        <>
          <FormField
            label="Runtime Variable"
            description="Name of the runtime variable to compare (captured from previous retrieve_value steps)"
          >
            <Select
              selectedOption={
                assertionVariable ?
                  { label: assertionVariable, value: assertionVariable } :
                  null
              }
              onChange={({ detail }) => onAssertionVariableChange(detail.selectedOption?.value || '')}
              options={existingSteps
                .filter(step => step.step_type === 'retrieve_value' && step.capture_variable)
                .map(step => ({
                  label: step.capture_variable,
                  value: step.capture_variable,
                  description: `From step ${step.sort}: ${step.instruction}`
                }))
                .sort((a, b) => a.label.localeCompare(b.label))}
              placeholder="Select a runtime variable"
              empty="No runtime variables available. Add retrieve_value steps first."
              filteringType="auto"
              disabled={disabled}
            />
          </FormField>

          <FormField label="Validation Type">
            <Select
              selectedOption={VALIDATION_TYPE_OPTIONS.find(opt => opt.value === validationType) || null}
              onChange={({ detail }) => {
                const newType = detail.selectedOption?.value || 'bool';
                onValidationTypeChange(newType);
                onValidationValueChange('');
                onBooleanInputModeChange('true');
                // Reset operator to first available option for the new type
                if (newType === 'string') {
                  onValidationOperatorChange('exact');
                } else if (newType === 'number') {
                  onValidationOperatorChange('equals');
                }
              }}
              options={VALIDATION_TYPE_OPTIONS}
              disabled={disabled}
            />
          </FormField>

          {validationType === 'bool' && (
            <>
              <FormField
                label="Expected Boolean Value"
                description="Select true/false or use a variable"
              >
                <Select
                  selectedOption={BOOLEAN_OPTIONS.find(opt => opt.value === booleanInputMode) || null}
                  onChange={({ detail }) => {
                    const mode = detail.selectedOption?.value || 'true';
                    onBooleanInputModeChange(mode);
                    if (mode === 'true' || mode === 'false') {
                      onValidationValueChange(mode);
                    } else {
                      onValidationValueChange('');
                    }
                  }}
                  options={BOOLEAN_OPTIONS}
                  disabled={disabled}
                />
              </FormField>
              {booleanInputMode === 'variable' && (
                <FormField
                  label="Variable Expression"
                  description="Enter a variable that evaluates to a boolean (e.g., {{myBooleanVar}})"
                >
                  <Input
                    value={validationValue}
                    onChange={({ detail }) => onValidationValueChange(detail.value)}
                    placeholder="{{myBooleanVar}}"
                    disabled={disabled}
                  />
                </FormField>
              )}
            </>
          )}

          {(validationType === 'string' || validationType === 'number') && (
            <>
              <FormField label="Comparison Operator">
                <Select
                  selectedOption={
                    VALIDATION_OPERATOR_OPTIONS[validationType as keyof typeof VALIDATION_OPERATOR_OPTIONS]
                      ?.find(opt => opt.value === validationOperator) || null
                  }
                  onChange={({ detail }) => onValidationOperatorChange(detail.selectedOption?.value ||
                    (validationType === 'string' ? 'exact' : 'equals'))}
                  options={VALIDATION_OPERATOR_OPTIONS[validationType as keyof typeof VALIDATION_OPERATOR_OPTIONS] || []}
                  disabled={disabled}
                />
              </FormField>

              <FormField
                label="Expected Value"
                description={
                  validationType === 'number'
                    ? 'Enter a numeric value. You can use variables like {{UniqueID}}, {{Time}}, {{ExecutionID}}, or custom variables.'
                    : 'Enter the expected text value. You can use variables like {{UniqueID}}, {{Time}}, {{ExecutionID}}, or custom variables.'
                }
              >
                <Input
                  value={validationValue}
                  onChange={({ detail }) => onValidationValueChange(detail.value)}
                  placeholder={
                    validationType === 'number'
                      ? 'Enter a number (e.g., 42, 3.14) or use variables like {{UniqueID}}'
                      : 'Enter expected value or use variables like {{UniqueID}}, {{Time}}'
                  }
                  type="text"
                  disabled={disabled}
                />
              </FormField>
            </>
          )}
        </>
      )}
    </SpaceBetween>
  );
}
