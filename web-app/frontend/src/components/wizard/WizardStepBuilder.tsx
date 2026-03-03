import { useState } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Alert from "@cloudscape-design/components/alert";
import StepForm from './StepForm';

interface WizardStepBuilderProps {
  onAddStep: (stepData: any) => Promise<void>;
  disabled?: boolean;
  usecaseId: string;
  existingSteps?: any[];
}

export default function WizardStepBuilder({ 
  onAddStep, 
  disabled = false,
  usecaseId,
  existingSteps = []
}: WizardStepBuilderProps) {
  const [stepType, setStepType] = useState('navigation');
  const [instruction, setInstruction] = useState('');
  const [selectedSecret, setSelectedSecret] = useState('');
  const [validationType, setValidationType] = useState('bool');
  const [validationOperator, setValidationOperator] = useState('exact');
  const [validationValue, setValidationValue] = useState('');
  const [captureVariable, setCaptureVariable] = useState('');
  const [valueType, setValueType] = useState('string');
  const [assertionVariable, setAssertionVariable] = useState('');
  const [booleanInputMode, setBooleanInputMode] = useState('true');
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (stepType !== 'assertion' && !instruction.trim()) {
      setError('Instruction is required');
      return;
    }
    if (stepType === 'assertion' && !assertionVariable.trim()) {
      setError('Runtime variable is required for assertion');
      return;
    }

    setAdding(true);
    setError(null);

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

      await onAddStep(stepData);

      // Reset form
      setInstruction('');
      setSelectedSecret('');
      setValidationValue('');
      setCaptureVariable('');
      setAssertionVariable('');
      setBooleanInputMode('true');
    } catch (err: any) {
      setError(err.message || 'Failed to add step');
    } finally {
      setAdding(false);
    }
  };

  const handleStepTypeChange = (value: string) => {
    setStepType(value);
    // Reset all dependent fields when changing type
    setSelectedSecret('');
    setValidationType('bool');
    setValidationOperator('exact');
    setValidationValue('');
    setCaptureVariable('');
    setValueType('string');
    setAssertionVariable('');
    setBooleanInputMode('true');
  };

  return (
    <Container
      header={
        <Header variant="h2">
          Add Step
        </Header>
      }
    >
      <SpaceBetween direction="vertical" size="m">
        {error && (
          <Alert
            type="error"
            dismissible
            onDismiss={() => setError(null)}
          >
            {error}
          </Alert>
        )}

        <StepForm
          usecaseId={usecaseId}
          stepType={stepType}
          instruction={instruction}
          selectedSecret={selectedSecret}
          validationType={validationType}
          validationOperator={validationOperator}
          validationValue={validationValue}
          captureVariable={captureVariable}
          valueType={valueType}
          assertionVariable={assertionVariable}
          booleanInputMode={booleanInputMode}
          existingSteps={existingSteps}
          disabled={disabled}
          onStepTypeChange={handleStepTypeChange}
          onInstructionChange={setInstruction}
          onSelectedSecretChange={setSelectedSecret}
          onValidationTypeChange={setValidationType}
          onValidationOperatorChange={setValidationOperator}
          onValidationValueChange={setValidationValue}
          onCaptureVariableChange={setCaptureVariable}
          onValueTypeChange={setValueType}
          onAssertionVariableChange={setAssertionVariable}
          onBooleanInputModeChange={setBooleanInputMode}
        />

        <Button
          variant="primary"
          onClick={handleSubmit}
          loading={adding}
          disabled={disabled || (stepType !== 'assertion' && !instruction.trim()) || (stepType === 'assertion' && !assertionVariable.trim())}
          fullWidth
        >
          Add & Execute Step
        </Button>
      </SpaceBetween>
    </Container>
  );
}
