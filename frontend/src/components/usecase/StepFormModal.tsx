import { useState, useEffect } from 'react';
import Modal from "@cloudscape-design/components/modal";
import Box from "@cloudscape-design/components/box";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import FormField from "@cloudscape-design/components/form-field";
import Select from "@cloudscape-design/components/select";
import Textarea from "@cloudscape-design/components/textarea";
import Input from "@cloudscape-design/components/input";
import SegmentedControl from "@cloudscape-design/components/segmented-control";
import { api } from '../../utils/api';

interface StepFormModalProps {
  visible: boolean;
  onDismiss: () => void;
  onSubmit: (stepData: any) => Promise<void>;
  step?: any; // For editing existing steps
  usecaseId: string;
  title: string;
  existingSteps?: any[]; // For runtime variable suggestions
}

const STEP_TYPE_OPTIONS = [
  { text: 'Navigation', id: 'navigation' },
  { text: 'URL', id: 'url' },
  { text: 'Secret', id: 'secret' },
  { text: 'Validation', id: 'validation' },
  { text: 'Retrieve Value', id: 'retrieve_value' },
  { text: 'Assertion', id: 'assertion' }
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



export default function StepFormModal({
  visible,
  onDismiss,
  onSubmit,
  step,
  usecaseId,
  title,
  existingSteps = []
}: StepFormModalProps) {
  const [stepType, setStepType] = useState('navigation');
  const [instruction, setInstruction] = useState('');
  const [selectedSecret, setSelectedSecret] = useState('');
  const [validationType, setValidationType] = useState('bool');
  const [validationOperator, setValidationOperator] = useState('exact');
  const [validationValue, setValidationValue] = useState('');
  const [availableSecrets, setAvailableSecrets] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);
  const [captureVariable, setCaptureVariable] = useState('');
  const [valueType, setValueType] = useState('string');
  const [assertionVariable, setAssertionVariable] = useState('');
  const [booleanInputMode, setBooleanInputMode] = useState('true');

  // Get available runtime variables from existing retrieve_value steps
  const getAvailableRuntimeVariables = () => {
    return existingSteps
      .filter(step => step.step_type === 'retrieve_value' && step.capture_variable)
      .map(step => ({
        label: step.capture_variable,
        value: step.capture_variable,
        description: `From step ${step.sort}: ${step.instruction}`
      }))
      .sort((a, b) => a.label.localeCompare(b.label));
  };

  // Initialize form with step data for editing
  useEffect(() => {
    if (step) {
      setStepType(step.step_type || 'navigation');
      setInstruction(step.instruction || '');
      setSelectedSecret(step.secret_key || '');
      setValidationType(step.validation_type || 'bool');
      setValidationOperator(step.validation_operator || 'exact');
      setValidationValue(step.validation_value || '');
      setCaptureVariable(step.capture_variable || '');
      setValueType(step.value_type || 'string');
      setAssertionVariable(step.assertion_variable || '');
      // Initialize boolean input mode based on existing value
      if (step.validation_value && (step.validation_value === 'true' || step.validation_value === 'false')) {
        setBooleanInputMode(step.validation_value);
      } else if (step.validation_value && step.validation_value.includes('{{')) {
        setBooleanInputMode('variable');
      } else {
        setBooleanInputMode('true');
      }
    } else {
      // Reset form for new step
      setStepType('navigation');
      setInstruction('');
      setSelectedSecret('');
      setValidationType('bool');
      setValidationOperator('exact');
      setValidationValue('');
      setCaptureVariable('');
      setValueType('string');
      setAssertionVariable('');
      setBooleanInputMode('true');
    }
  }, [step]);

  // Load available secrets when modal opens or step type changes to secret
  useEffect(() => {
    if (visible && stepType === 'secret') {
      loadSecrets();
    }
  }, [visible, stepType, usecaseId]);

  const loadSecrets = async () => {
    try {
      const response = await api.get(`usecase/${usecaseId}/secrets`);
      setAvailableSecrets(response.secrets || []);
    } catch (error) {
      console.error('Failed to load secrets:', error);
      setAvailableSecrets([]);
    }
  };

  const handleSubmit = async () => {
    if (stepType !== 'assertion' && !instruction.trim()) return;
    if (stepType === 'secret' && !selectedSecret) return;
    if (stepType === 'validation' && validationType === 'string' && !validationValue.trim()) return;
    if (stepType === 'validation' && validationType === 'number' && !validationValue.trim()) return;
    if (stepType === 'validation' && validationType === 'bool' && !validationValue.trim()) return;
    if (stepType === 'retrieve_value' && !captureVariable.trim()) return;
    if (stepType === 'assertion' && !assertionVariable.trim()) return;
    if (stepType === 'assertion' && validationType === 'string' && !validationValue.trim()) return;
    if (stepType === 'assertion' && validationType === 'number' && !validationValue.trim()) return;
    if (stepType === 'assertion' && validationType === 'bool' && !validationValue.trim()) return;

    setSaving(true);
    try {
      const stepData: any = {
        instruction: stepType === 'assertion' ? (instruction.trim() || 'Assertion step') : instruction.trim(),
        step_type: stepType
      };

      if (stepType === 'secret') {
        stepData.secret_key = selectedSecret;
      } else if (stepType === 'validation') {
        stepData.validation_type = validationType;
        stepData.validation_operator = validationOperator;
        stepData.validation_value = validationValue.trim();
        stepData.operator = validationOperator;
      } else if (stepType === 'retrieve_value') {
        stepData.capture_variable = captureVariable.trim();
        stepData.value_type = valueType;
      } else if (stepType === 'assertion') {
        stepData.assertion_variable = assertionVariable.trim();
        stepData.validation_type = validationType;
        stepData.validation_operator = validationOperator;
        stepData.validation_value = validationValue.trim();
      }

      // Ensure other step types don't have these fields
      if (stepType !== 'retrieve_value') {
        stepData.capture_variable = '';
        stepData.value_type = '';
      }

      await onSubmit(stepData);
      onDismiss();
    } catch (error) {
      console.error('Failed to save step:', error);
    } finally {
      setSaving(false);
    }
  };

  const isFormValid = () => {
    if (stepType !== 'assertion' && !instruction.trim()) return false;
    if (stepType === 'secret' && !selectedSecret) return false;
    if (stepType === 'validation' && validationType === 'string' && !validationValue.trim()) return false;
    if (stepType === 'validation' && validationType === 'number' && !validationValue.trim()) return false;
    if (stepType === 'validation' && validationType === 'bool' && !validationValue.trim()) return false;
    if (stepType === 'retrieve_value' && !captureVariable.trim()) return false;
    if (stepType === 'assertion' && !assertionVariable.trim()) return false;
    if (stepType === 'assertion' && validationType === 'string' && !validationValue.trim()) return false;
    if (stepType === 'assertion' && validationType === 'number' && !validationValue.trim()) return false;
    if (stepType === 'assertion' && validationType === 'bool' && !validationValue.trim()) return false;
    return true;
  };

  return (
    <Modal
      onDismiss={onDismiss}
      visible={visible}
      closeAriaLabel="Close modal"
      size="large"
      header={title}
      footer={
        <Box float="right">
          <Button variant="link" onClick={onDismiss}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSubmit}
            loading={saving}
            disabled={!isFormValid() || saving}
          >
            {step ? 'Update Step' : 'Create Step'}
          </Button>
        </Box>
      }
    >
      <SpaceBetween direction="vertical" size="l">
        <FormField label="Step Type" stretch>
          <SegmentedControl
            selectedId={stepType}
            onChange={({ detail }) => {
              setStepType(detail.selectedId);
              // Reset all dependent fields when changing type
              setSelectedSecret('');
              setValidationType('bool');
              setValidationOperator('exact');
              setValidationValue('');
              setCaptureVariable('');
              setValueType('string');
            }}
            options={STEP_TYPE_OPTIONS}
          />
        </FormField>

        {stepType !== 'assertion' && (
          <FormField
            stretch
            label="Instruction"
            description={
              stepType === 'navigation' ? 'Describe the action to perform on the page' :
                stepType === 'url' ? 'Enter the URL to navigate to (e.g., "https://example.com/login")' :
                  stepType === 'secret' ? 'Describe the action (e.g., "Type password in login field")' :
                    stepType === 'validation' ? 'Describe what should be validated on the page' :
                      'Describe what value to retrieve from the page'
            }
          >
            <Textarea
              value={instruction}
              onChange={({ detail }) => setInstruction(detail.value)}
              placeholder={
                stepType === 'navigation' ? 'Enter navigation instruction' :
                  stepType === 'url' ? 'https://example.com/page' :
                    stepType === 'secret' ? 'Describe the action with the secret' :
                      stepType === 'validation' ? 'Describe the validation to perform' :
                        'Describe what to retrieve (e.g., "Get the product price")'
              }
              rows={3}
            />
          </FormField>
        )}

        {stepType === 'secret' && (
          <FormField
            stretch
            label="Select Secret"
            description="Choose which secret to use for this step"
          >
            <Select
              selectedOption={availableSecrets.find(secret => secret.key === selectedSecret) ?
                { label: availableSecrets.find(secret => secret.key === selectedSecret)?.key || '', value: selectedSecret } :
                null
              }
              onChange={({ detail }) => setSelectedSecret(detail.selectedOption?.value || '')}
              options={availableSecrets.map(secret => ({
                label: secret.key,
                value: secret.key,
                description: secret.description
              }))}
              placeholder="Select a secret"
              empty="No secrets available. Create secrets first."
            />
          </FormField>
        )}

        {stepType === 'validation' && (
          <>
            <FormField label="Validation Type" stretch>
              <Select
                selectedOption={VALIDATION_TYPE_OPTIONS.find(opt => opt.value === validationType) || null}
                onChange={({ detail }) => {
                  const newType = detail.selectedOption?.value || 'bool';
                  setValidationType(newType);
                  setValidationValue('');
                  setBooleanInputMode('true');
                  // Reset operator to first available option for the new type
                  if (newType === 'string') {
                    setValidationOperator('exact');
                  } else if (newType === 'number') {
                    setValidationOperator('equals');
                  }
                }}
                options={VALIDATION_TYPE_OPTIONS}
              />
            </FormField>

            {validationType === 'bool' && (
              <>
                <FormField
                  stretch
                  label="Expected Boolean Value"
                  description="Select true/false or use a variable"
                >
                  <Select
                    selectedOption={BOOLEAN_OPTIONS.find(opt => opt.value === booleanInputMode) || null}
                    onChange={({ detail }) => {
                      const mode = detail.selectedOption?.value || 'true';
                      setBooleanInputMode(mode);
                      if (mode === 'true' || mode === 'false') {
                        setValidationValue(mode);
                      } else {
                        setValidationValue('');
                      }
                    }}
                    options={BOOLEAN_OPTIONS}
                  />
                </FormField>
                {booleanInputMode === 'variable' && (
                  <FormField
                    stretch
                    label="Variable Expression"
                    description="Enter a variable that evaluates to a boolean (e.g., {{myBooleanVar}})"
                  >
                    <Input
                      value={validationValue}
                      onChange={({ detail }) => setValidationValue(detail.value)}
                      placeholder="{{myBooleanVar}}"
                    />
                  </FormField>
                )}
              </>
            )}

            {(validationType === 'string' || validationType === 'number') && (
              <>
                <FormField label="Comparison Operator" stretch>
                  <Select
                    selectedOption={
                      VALIDATION_OPERATOR_OPTIONS[validationType as keyof typeof VALIDATION_OPERATOR_OPTIONS]
                        ?.find(opt => opt.value === validationOperator) || null
                    }
                    onChange={({ detail }) => setValidationOperator(detail.selectedOption?.value ||
                      (validationType === 'string' ? 'exact' : 'equals'))}
                    options={VALIDATION_OPERATOR_OPTIONS[validationType as keyof typeof VALIDATION_OPERATOR_OPTIONS] || []}
                  />
                </FormField>

                <FormField
                  stretch
                  label="Expected Value"
                  description={
                    validationType === 'number'
                      ? 'Enter a numeric value. You can use variables like {{UniqueID}}, {{Time}}, {{ExecutionID}}, or custom variables.'
                      : 'Enter the expected text value. You can use variables like {{UniqueID}}, {{Time}}, {{ExecutionID}}, or custom variables.'
                  }
                >
                  <Input
                    value={validationValue}
                    onChange={({ detail }) => {
                      console.log(typeof detail.value.toString())
                      setValidationValue(detail.value.toString())
                    }}
                    placeholder={
                      validationType === 'number'
                        ? 'Enter a number (e.g., 42, 3.14) or use variables like {{UniqueID}}'
                        : 'Enter expected value or use variables like {{UniqueID}}, {{Time}}'
                    }
                    type="text"
                  />
                </FormField>
              </>
            )}
          </>
        )}

        {stepType === 'retrieve_value' && (
          <>
            <FormField
              stretch
              label="Variable Name"
              description="Name for the captured variable (will be available as {{variableName}} in subsequent steps)"
            >
              <Input
                value={captureVariable}
                onChange={({ detail }) => setCaptureVariable(detail.value)}
                placeholder="e.g., product_price, user_id, status"
              />
            </FormField>

            <FormField
              stretch
              label="Value Type"
              description="Expected type of the retrieved value"
            >
              <Select
                selectedOption={VALUE_TYPE_OPTIONS.find(opt => opt.value === valueType) || null}
                onChange={({ detail }) => setValueType(detail.selectedOption?.value || 'string')}
                options={VALUE_TYPE_OPTIONS}
              />
            </FormField>
          </>
        )}

        {stepType === 'assertion' && (
          <>
            <FormField
              stretch
              label="Runtime Variable"
              description="Name of the runtime variable to compare (captured from previous retrieve_value steps)"
            >
              <Select
                selectedOption={
                  assertionVariable ?
                    { label: assertionVariable, value: assertionVariable } :
                    null
                }
                onChange={({ detail }) => setAssertionVariable(detail.selectedOption?.value || '')}
                options={getAvailableRuntimeVariables()}
                placeholder="Select a runtime variable"
                empty="No runtime variables available. Add retrieve_value steps first."
                filteringType="auto"
                expandToViewport={true}
              />
            </FormField>

            <FormField label="Validation Type" stretch>
              <Select
                selectedOption={VALIDATION_TYPE_OPTIONS.find(opt => opt.value === validationType) || null}
                onChange={({ detail }) => {
                  const newType = detail.selectedOption?.value || 'bool';
                  setValidationType(newType);
                  setValidationValue('');
                  setBooleanInputMode('true');
                  // Reset operator to first available option for the new type
                  if (newType === 'string') {
                    setValidationOperator('exact');
                  } else if (newType === 'number') {
                    setValidationOperator('equals');
                  }
                }}
                options={VALIDATION_TYPE_OPTIONS}
              />
            </FormField>

            {validationType === 'bool' && (
              <>
                <FormField
                  stretch
                  label="Expected Boolean Value"
                  description="Select true/false or use a variable"
                >
                  <Select
                    selectedOption={BOOLEAN_OPTIONS.find(opt => opt.value === booleanInputMode) || null}
                    onChange={({ detail }) => {
                      const mode = detail.selectedOption?.value || 'true';
                      setBooleanInputMode(mode);
                      if (mode === 'true' || mode === 'false') {
                        setValidationValue(mode);
                      } else {
                        setValidationValue('');
                      }
                    }}
                    options={BOOLEAN_OPTIONS}
                  />
                </FormField>
                {booleanInputMode === 'variable' && (
                  <FormField
                    stretch
                    label="Variable Expression"
                    description="Enter a variable that evaluates to a boolean (e.g., {{myBooleanVar}})"
                  >
                    <Input
                      value={validationValue}
                      onChange={({ detail }) => setValidationValue(detail.value)}
                      placeholder="{{myBooleanVar}}"
                    />
                  </FormField>
                )}
              </>
            )}

            {(validationType === 'string' || validationType === 'number') && (
              <>
                <FormField label="Comparison Operator" stretch>
                  <Select
                    selectedOption={
                      VALIDATION_OPERATOR_OPTIONS[validationType as keyof typeof VALIDATION_OPERATOR_OPTIONS]
                        ?.find(opt => opt.value === validationOperator) || null
                    }
                    onChange={({ detail }) => setValidationOperator(detail.selectedOption?.value ||
                      (validationType === 'string' ? 'exact' : 'equals'))}
                    options={VALIDATION_OPERATOR_OPTIONS[validationType as keyof typeof VALIDATION_OPERATOR_OPTIONS] || []}
                  />
                </FormField>

                <FormField
                  stretch
                  label="Expected Value"
                  description={
                    validationType === 'number'
                      ? 'Enter a numeric value. You can use variables like {{UniqueID}}, {{Time}}, {{ExecutionID}}, or custom variables.'
                      : 'Enter the expected text value. You can use variables like {{UniqueID}}, {{Time}}, {{ExecutionID}}, or custom variables.'
                  }
                >
                  <Input
                    value={validationValue}
                    onChange={({ detail }) => {
                      console.log(typeof detail.value.toString())
                      setValidationValue(detail.value.toString())
                    }}
                    placeholder={
                      validationType === 'number'
                        ? 'Enter a number (e.g., 42, 3.14) or use variables like {{UniqueID}}'
                        : 'Enter expected value or use variables like {{UniqueID}}, {{Time}}'
                    }
                    type="text"
                  />
                </FormField>
              </>
            )}
          </>
        )}
      </SpaceBetween>
    </Modal>
  );
}