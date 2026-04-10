import { useState, useEffect } from 'react';
import Modal from "@cloudscape-design/components/modal";
import Box from "@cloudscape-design/components/box";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import FormField from "@cloudscape-design/components/form-field";
import Select from "@cloudscape-design/components/select";
import Textarea from "@cloudscape-design/components/textarea";
import Input from "@cloudscape-design/components/input";
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import Link from "@cloudscape-design/components/link";
import Spinner from "@cloudscape-design/components/spinner";
import ExpandableSection from "@cloudscape-design/components/expandable-section";
import Checkbox from "@cloudscape-design/components/checkbox";
import Alert from "@cloudscape-design/components/alert";
import { api } from '../../utils/api';

interface StepFormModalProps {
  visible: boolean;
  onDismiss: () => void;
  onSubmit: (stepData: any) => Promise<void>;
  onUpdateFromTemplate?: () => Promise<void>;
  step?: any; // For editing existing steps
  usecaseId: string;
  title: string;
  existingSteps?: any[]; // For runtime variable suggestions
}

const STEP_TYPE_OPTIONS = [
  { label: 'Navigation', value: 'navigation' },
  { label: 'URL', value: 'url' },
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



export default function StepFormModal({
  visible,
  onDismiss,
  onSubmit,
  onUpdateFromTemplate,
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
  const [valueSource, setValueSource] = useState('screen');
  const [assertionVariable, setAssertionVariable] = useState('');
  const [booleanInputMode, setBooleanInputMode] = useState('true');
  const [updatingFromTemplate, setUpdatingFromTemplate] = useState(false);
  const [templateStep, setTemplateStep] = useState<any>(null);
  const [loadingTemplateStep, setLoadingTemplateStep] = useState(false);
  const [templateDifferences, setTemplateDifferences] = useState<Array<{field: string, current: any, template: any}>>([]);
  const [enableAdvancedClickTypes, setEnableAdvancedClickTypes] = useState(false);

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
      setValueSource(step.value_source || 'screen');
      setAssertionVariable(step.assertion_variable || '');
      setEnableAdvancedClickTypes(step.enable_advanced_click_types || false);
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
      setValueSource('screen');
      setAssertionVariable('');
      setBooleanInputMode('true');
      setEnableAdvancedClickTypes(false);
    }
  }, [step]);

  // Load available secrets when modal opens or step type changes to secret
  useEffect(() => {
    if (visible && stepType === 'secret') {
      loadSecrets();
    }
  }, [visible, stepType, usecaseId]);

  // Load template step data when modal opens with a step from a template
  useEffect(() => {
    if (visible && step?.template_id && step?.template_step_id) {
      loadTemplateStep();
    } else {
      setTemplateStep(null);
      setTemplateDifferences([]);
    }
  }, [visible, step?.template_id, step?.template_step_id]);

  const loadSecrets = async () => {
    try {
      const response = await api.get(`usecase/${usecaseId}/secrets`);
      setAvailableSecrets(response.secrets || []);
    } catch (error) {
      console.error('Failed to load secrets:', error);
      setAvailableSecrets([]);
    }
  };

  const loadTemplateStep = async () => {
    if (!step?.template_id || !step?.template_step_id) return;
    
    setLoadingTemplateStep(true);
    try {
      const response = await api.get(`templates/${step.template_id}/steps`);
      const steps = response.steps || [];
      const matchingStep = steps.find((s: any) => s.id === step.template_step_id);
      
      if (matchingStep) {
        setTemplateStep(matchingStep);
        calculateDifferences(step, matchingStep);
      }
    } catch (error) {
      console.error('Failed to load template step:', error);
      setTemplateStep(null);
    } finally {
      setLoadingTemplateStep(false);
    }
  };

  const calculateDifferences = (currentStep: any, templateStep: any) => {
    const diffs: Array<{field: string, current: any, template: any}> = [];
    
    // Helper to check if a value is empty (null, undefined, or empty string)
    const isEmpty = (val: any) => val === null || val === undefined || val === '';
    
    // Helper to check if values are different (ignoring empty values on both sides)
    const isDifferent = (current: any, template: any) => {
      const currentEmpty = isEmpty(current);
      const templateEmpty = isEmpty(template);
      
      // If both are empty, they're not different
      if (currentEmpty && templateEmpty) return false;
      
      // If one is empty and the other isn't, they're different
      if (currentEmpty !== templateEmpty) return true;
      
      // Compare actual values
      return current !== template;
    };
    
    // Always compare instruction and step_type
    if (isDifferent(currentStep.instruction, templateStep.instruction)) {
      diffs.push({
        field: 'Instruction',
        current: currentStep.instruction || '(empty)',
        template: templateStep.instruction || '(empty)'
      });
    }
    if (isDifferent(currentStep.step_type, templateStep.step_type)) {
      diffs.push({
        field: 'Step Type',
        current: currentStep.step_type || '(empty)',
        template: templateStep.step_type || '(empty)'
      });
    }
    
    // Only compare step-type-specific fields
    const stepType = templateStep.step_type || currentStep.step_type;
    
    if (stepType === 'secret' && isDifferent(currentStep.secret_key, templateStep.secret_key)) {
      diffs.push({
        field: 'Secret Key',
        current: currentStep.secret_key || '(empty)',
        template: templateStep.secret_key || '(empty)'
      });
    }
    
    if (stepType === 'retrieve_value') {
      if (isDifferent(currentStep.capture_variable, templateStep.capture_variable)) {
        diffs.push({
          field: 'Capture Variable',
          current: currentStep.capture_variable || '(empty)',
          template: templateStep.capture_variable || '(empty)'
        });
      }
      if (isDifferent(currentStep.value_type, templateStep.value_type)) {
        diffs.push({
          field: 'Value Type',
          current: currentStep.value_type || '(empty)',
          template: templateStep.value_type || '(empty)'
        });
      }
    }
    
    if (stepType === 'validation' || stepType === 'assertion') {
      if (isDifferent(currentStep.validation_type, templateStep.validation_type)) {
        diffs.push({
          field: 'Validation Type',
          current: currentStep.validation_type || '(empty)',
          template: templateStep.validation_type || '(empty)'
        });
      }
      if (isDifferent(currentStep.validation_operator, templateStep.validation_operator)) {
        diffs.push({
          field: 'Validation Operator',
          current: currentStep.validation_operator || '(empty)',
          template: templateStep.validation_operator || '(empty)'
        });
      }
      if (isDifferent(currentStep.validation_value, templateStep.validation_value)) {
        diffs.push({
          field: 'Validation Value',
          current: currentStep.validation_value || '(empty)',
          template: templateStep.validation_value || '(empty)'
        });
      }
    }
    
    if (stepType === 'assertion' && isDifferent(currentStep.assertion_variable, templateStep.assertion_variable)) {
      diffs.push({
        field: 'Assertion Variable',
        current: currentStep.assertion_variable || '(empty)',
        template: templateStep.assertion_variable || '(empty)'
      });
    }
    
    setTemplateDifferences(diffs);
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

      // Add advanced click types flag for navigation steps
      if (stepType === 'navigation') {
        stepData.enable_advanced_click_types = enableAdvancedClickTypes;
      }

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
        stepData.value_source = valueSource;
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

  const handleUpdateFromTemplate = async () => {
    if (!onUpdateFromTemplate) return;
    
    setUpdatingFromTemplate(true);
    try {
      await onUpdateFromTemplate();
      onDismiss();
    } catch (error) {
      console.error('Failed to update from template:', error);
    } finally {
      setUpdatingFromTemplate(false);
    }
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
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={onDismiss} disabled={saving || updatingFromTemplate}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleSubmit}
              loading={saving}
              disabled={!isFormValid() || saving || updatingFromTemplate}
            >
              {step ? 'Update Step' : 'Create Step'}
            </Button>
          </SpaceBetween>
        </Box>
      }
    >
      <SpaceBetween direction="vertical" size="l">
        <FormField
          stretch
          label="Step Type"
          description="Select the type of step to create"
        >
          <Select
            selectedOption={STEP_TYPE_OPTIONS.find(opt => opt.value === stepType) || null}
            onChange={({ detail }) => {
              setStepType(detail.selectedOption?.value || 'navigation');
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
                      stepType === 'download' ? 'Describe the action that triggers the download. Automatically handles downloads in popups or current page.' :
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
                        stepType === 'download' ? 'Click the download button' :
                            'Describe what to retrieve (e.g., "Get the product price")'
              }
              rows={3}
            />
          </FormField>
        )}

        {stepType === 'navigation' && (
          <Checkbox
            checked={enableAdvancedClickTypes}
            onChange={({ detail }) => setEnableAdvancedClickTypes(detail.checked)}
          >
            Enable advanced click types (double-click, right-click)
          </Checkbox>
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
              label="Value Source"
              description="Where to read the value from"
            >
              <Select
                selectedOption={{ label: valueSource === 'url' ? 'Page URL' : 'Screen (AI vision)', value: valueSource }}
                onChange={({ detail }) => setValueSource(detail.selectedOption?.value || 'screen')}
                options={[
                  { label: 'Screen (AI vision)', value: 'screen', description: 'Nova Act reads the value from the page visually' },
                  { label: 'Page URL', value: 'url', description: 'Extract from the current page URL using an optional regex pattern' },
                ]}
              />
            </FormField>

            {valueSource === 'url' && (
              <Alert type="info">
                The instruction field becomes a regex pattern. Use a capture group to extract a substring
                (e.g., <code>confirmationId=([A-Z0-9]+)</code>). Leave empty to capture the full URL.
              </Alert>
            )}

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

        {/* Template Info Section */}
        {step?.template_id && (
          <Container
            header={
              <Header variant="h3">
                Template Information
              </Header>
            }
          >
            <SpaceBetween direction="vertical" size="m">
              <div>
                <Box variant="awsui-key-label">Source Template</Box>
                <Link
                  href={`/templates/${step.template_id}`}
                  external
                  externalIconAriaLabel="Opens in new tab"
                >
                  View Template
                </Link>
                {step.template_version && (
                  <Box variant="span" color="text-body-secondary" margin={{ left: 'xs' }}>
                    (v{step.template_version})
                  </Box>
                )}
              </div>

              <div>
                <Box variant="awsui-key-label">Status</Box>
                {loadingTemplateStep ? (
                  <Box color="text-body-secondary">
                    <Spinner /> Checking for updates...
                  </Box>
                ) : templateDifferences.length > 0 ? (
                  <Box color="text-status-warning">
                    ⚠ Out of sync ({templateDifferences.length} {templateDifferences.length === 1 ? 'change' : 'changes'} detected)
                  </Box>
                ) : templateStep ? (
                  <Box color="text-status-success">
                    ✓ Up to date
                  </Box>
                ) : (
                  <Box color="text-body-secondary">
                    Unable to check status
                  </Box>
                )}
              </div>

              {templateDifferences.length > 0 && (
                <ExpandableSection headerText="View changes" variant="footer">
                  <SpaceBetween direction="vertical" size="s">
                    {templateDifferences.map((diff, index) => (
                      <Container key={index}>
                        <SpaceBetween direction="vertical" size="xs">
                          <Box variant="strong" color="text-label">{diff.field}</Box>
                          <div>
                            <Box 
                              padding={{ vertical: 'xs', horizontal: 's' }}
                              margin={{ bottom: 'xs' }}
                            >
                              <SpaceBetween direction="vertical" size="xxs">
                                <Box variant="small" color="text-status-warning">Current:</Box>
                                <Box variant="code">{diff.current}</Box>
                              </SpaceBetween>
                            </Box>
                            <Box 
                              padding={{ vertical: 'xs', horizontal: 's' }}
                            >
                              <SpaceBetween direction="vertical" size="xxs">
                                <Box variant="small" color="text-status-success">Template:</Box>
                                <Box variant="code">{diff.template}</Box>
                              </SpaceBetween>
                            </Box>
                          </div>
                        </SpaceBetween>
                      </Container>
                    ))}
                  </SpaceBetween>
                </ExpandableSection>
              )}

              {onUpdateFromTemplate && templateDifferences.length > 0 && (
                <Button
                  iconName="refresh"
                  onClick={handleUpdateFromTemplate}
                  loading={updatingFromTemplate}
                  disabled={updatingFromTemplate || saving}
                >
                  Update from Template
                </Button>
              )}
            </SpaceBetween>
          </Container>
        )}
      </SpaceBetween>
    </Modal>
  );
}