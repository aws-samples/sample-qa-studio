import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Box from "@cloudscape-design/components/box";
import Spinner from "@cloudscape-design/components/spinner";
import Alert from "@cloudscape-design/components/alert";
import { wizardApi, exportImportApi } from '../utils/api';
import { ErrorState, errorManager } from '../utils/errorManager';
import { useRetry } from '../utils/retryManager';
import { validationManager, WIZARD_FIELD_CONFIGS } from '../utils/validation';
import ErrorDisplay from './common/ErrorDisplay';
import FormValidationSummary from './common/FormValidationSummary';
import FormField from "@cloudscape-design/components/form-field";
import Input from "@cloudscape-design/components/input";
import Textarea from "@cloudscape-design/components/textarea";
import UsecasePreview from './UserJourneyWizard/UsecasePreview';
import Popover from "@cloudscape-design/components/popover";
import LoadingBar from "@cloudscape-design/chat-components/loading-bar";
import Select, { SelectProps } from "@cloudscape-design/components/select";
import LiveRegion from "@cloudscape-design/components/live-region";
import { regionOptions, findRegionOptions } from './../utils/browser_regions'

interface UserJourneyWizardProps {
  onUsecaseCreated?: (usecaseId: string) => void;
}

interface WizardState {
  formData: {
    title: string;
    startingUrl: string;
    userJourney: string;
    executionRegion: string;
  };
  isGenerating: boolean;
  isImporting: boolean;
  generatedUsecase: any | null;
  previewMode: boolean;
  error: ErrorState | null;
  validationErrors: Record<string, string>;
  validationWarnings: Record<string, string>;
  importSuccess: {
    usecaseId: string;
    missingSecrets?: string[];
  } | null;
}

export default function UserJourneyWizard({ onUsecaseCreated }: UserJourneyWizardProps) {
  const navigate = useNavigate();
  const { executeWithRetry } = useRetry();
  const [state, setState] = useState<WizardState>({
    formData: {
      title: '',
      startingUrl: '',
      userJourney: '',
      executionRegion: 'eu-central-1'
    },
    isGenerating: false,
    isImporting: false,
    generatedUsecase: null,
    previewMode: false,
    error: null,
    validationErrors: {},
    validationWarnings: {},
    importSuccess: null
  });


  const validateForm = (): boolean => {
    const validation = validationManager.validateForm(state.formData, WIZARD_FIELD_CONFIGS);
    
    setState(prev => ({
      ...prev,
      validationErrors: validation.errors,
      validationWarnings: validation.warnings
    }));
    
    return validation.isValid;
  };

  const handleFieldChange = (field: keyof WizardState['formData'], value: string) => {
    setState(prev => ({
      ...prev,
      formData: { ...prev.formData, [field]: value },
      // Clear previous validation errors for this field
      validationErrors: { ...prev.validationErrors, [field]: '' },
      validationWarnings: { ...prev.validationWarnings, [field]: '' }
    }));
  };

  const handleGenerateUsecase = async () => {
    if (!validateForm()) {
      return;
    }

    setState(prev => ({ ...prev, isGenerating: true, error: null }));

    try {
      const response = await wizardApi.generateUsecase({
        title: state.formData.title,
        startingUrl: state.formData.startingUrl,
        userJourney: state.formData.userJourney,
        region: state.formData.executionRegion
      });

      if (response.success) {
        const usecaseData = JSON.parse(response.usecaseData);
        setState(prev => ({
          ...prev,
          generatedUsecase: usecaseData,
          previewMode: true,
          isGenerating: false
        }));
      } else {
        throw errorManager.createError('bedrock', 
          response.error || 'Failed to generate use case');
      }
    } catch (error) {
      console.error('Failed to generate use case:', error);
      
      // Convert to ErrorState if needed
      const errorState = (error as ErrorState).type 
        ? error as ErrorState 
        : errorManager.createError('unknown', 
            'An unexpected error occurred while generating the use case');
      
      setState(prev => ({
        ...prev,
        error: errorState,
        isGenerating: false
      }));
    }
  };

  const handleImportUsecase = async () => {
    if (!state.generatedUsecase) return;

    setState(prev => ({ ...prev, isImporting: true, error: null }));

    const result = await executeWithRetry(
      () => exportImportApi.importUsecase(state.generatedUsecase),
      { maxRetries: 2 }
    );

    if (result.success) {
      const response = result.data;
      
      if (response.success) {
        const usecaseId = response.usecaseId;
        
        // Show success message if there are missing secrets, otherwise navigate immediately
        if (response.missingSecrets && response.missingSecrets.length > 0) {
          setState(prev => ({
            ...prev,
            importSuccess: {
              usecaseId,
              missingSecrets: response.missingSecrets
            },
            isImporting: false
          }));
        } else {
          // Clear form for reuse
          setState(prev => ({
            ...prev,
            formData: { title: '', startingUrl: '', userJourney: '', executionRegion: '' },
            generatedUsecase: null,
            previewMode: false,
            isImporting: false,
            isGenerating: false,
            validationErrors: {},
            validationWarnings: {},
            importSuccess: null
          }));

          // Notify parent component if callback provided
          if (onUsecaseCreated) {
            onUsecaseCreated(usecaseId);
          }

          // Navigate to the new use case
          navigate(`/usecase/${usecaseId}`);
        }
      } else {
        const error = errorManager.createError('import', 
          response.error || 'Failed to import use case',
          {
            details: response.missingSecrets && response.missingSecrets.length > 0 
              ? `Note: The following secrets need to be configured: ${response.missingSecrets.join(', ')}`
              : undefined
          }
        );
        setState(prev => ({ ...prev, error, isImporting: false }));
      }
    } else {
      console.error('Failed to import use case:', result.error);
      
      // Enhance import-specific errors
      const error = result.error || errorManager.createError('import', 
        'Failed to import the generated use case');
      
      if (error.type === 'network') {
        error.type = 'import';
        error.message = 'Failed to save the generated use case. Please try again.';
      }
      
      setState(prev => ({ ...prev, error, isImporting: false }));
    }
  };

  const handleRegenerate = () => {
    setState(prev => ({
      ...prev,
      generatedUsecase: null,
      previewMode: false,
      error: null,
      importSuccess: null
    }));
  };

  const handleRetry = () => {
    if (state.previewMode) {
      handleImportUsecase();
    } else {
      handleGenerateUsecase();
    }
  };

  const handleDismissError = () => {
    setState(prev => ({ ...prev, error: null }));
  };

  const isFormValid = () => {
    // Check if there are any validation errors
    if (Object.keys(state.validationErrors).some(key => state.validationErrors[key])) {
      return false;
    }
    
    // Check if all required fields have values
    return Object.keys(WIZARD_FIELD_CONFIGS).every(field => {
      const config = WIZARD_FIELD_CONFIGS[field];
      const value = state.formData[field as keyof typeof state.formData];
      
      if (config.rules.required) {
        return value && value.trim().length > 0;
      }
      
      return true;
    });
  };

  if (state.previewMode && state.generatedUsecase) {
    return (
      <Container header={<Header variant="h1">User Journey Wizard - Preview</Header>}>
        <UsecasePreview
          usecase={state.generatedUsecase}
          onImport={handleImportUsecase}
          onRegenerate={handleRegenerate}
          isImporting={state.isImporting}
        />
        {state.importSuccess && (
          <Box margin={{ top: 'l' }}>
            <Alert 
              type="success" 
              dismissible 
              onDismiss={() => setState(prev => ({ ...prev, importSuccess: null }))}
              action={
                <Button 
                  variant="primary"
                  onClick={() => {
                    if (state.importSuccess) {
                      navigate(`/usecase/${state.importSuccess.usecaseId}`);
                    }
                  }}
                >
                  Go to Use Case
                </Button>
              }
            >
              <SpaceBetween direction="vertical" size="xs">
                <Box variant="strong">Use case imported successfully!</Box>
                {state.importSuccess.missingSecrets && state.importSuccess.missingSecrets.length > 0 && (
                  <Box variant="small">
                    <strong>Note:</strong> The following secrets need to be configured in the imported use case:
                    <ul style={{ margin: '4px 0', paddingLeft: '20px' }}>
                      {state.importSuccess.missingSecrets.map((secret: string) => (
                        <li key={secret}>{secret}</li>
                      ))}
                    </ul>
                  </Box>
                )}
              </SpaceBetween>
            </Alert>
          </Box>
        )}
        {state.error && (
          <Box margin={{ top: 'l' }}>
            <ErrorDisplay
              error={state.error}
              onRetry={handleRetry}
              onDismiss={handleDismissError}
              isRetrying={state.isImporting}
            />
          </Box>
        )}
      </Container>
    );
  }

  return (
    <Container header={
      <Header 
        variant="h1"
        description="Create automated test use cases by describing your user journey in natural language"
      >
        User Journey Wizard
      </Header>
    }>
      <SpaceBetween direction="vertical" size="l">
        {state.error && (
          <ErrorDisplay
            error={state.error}
            onRetry={handleRetry}
            onDismiss={handleDismissError}
            isRetrying={state.isGenerating || state.isImporting}
          />
        )}

        <FormField
          label={
            <SpaceBetween direction="horizontal" size="xs" alignItems="center">
              <span>Title</span>
              <Popover
                size="medium"
                position="right"
                triggerType="custom"
                dismissButton={false}
                content={
                  <SpaceBetween direction="vertical" size="xs">
                    <Box variant="strong">Examples:</Box>
                    <Box variant="small">• User Login Flow Test</Box>
                    <Box variant="small">• E-commerce Checkout Process</Box>
                    <Box variant="small">• Account Registration Validation</Box>
                  </SpaceBetween>
                }
              >
                <Button variant="inline-icon" iconName="status-info" />
              </Popover>
            </SpaceBetween>
          }
          errorText={state.validationErrors.title}
        >
          <Input
            value={state.formData.title}
            onChange={({ detail }) => handleFieldChange('title', detail.value)}
            placeholder="e.g., User Login Flow Test"
            disabled={state.isGenerating}
            invalid={!!state.validationErrors.title}
          />
        </FormField>
        
        <FormField
          label={
            <SpaceBetween direction="horizontal" size="xs" alignItems="center">
              <span>Starting URL</span>
              <Popover
                size="medium"
                position="right"
                triggerType="custom"
                dismissButton={false}
                content={
                  <SpaceBetween direction="vertical" size="xs">
                    <Box variant="strong">Examples:</Box>
                    <Box variant="small">• https://example.com/login</Box>
                    <Box variant="small">• https://shop.example.com</Box>
                    <Box variant="small">• https://app.example.com/signup</Box>
                  </SpaceBetween>
                }
              >
                <Button variant="inline-icon" iconName="status-info" />
              </Popover>
            </SpaceBetween>
          }
          errorText={state.validationErrors.startingUrl}
        >
          <Input
            value={state.formData.startingUrl}
            onChange={({ detail }) => handleFieldChange('startingUrl', detail.value)}
            placeholder="https://example.com/login"
            disabled={state.isGenerating}
            invalid={!!state.validationErrors.startingUrl}
          />
        </FormField>

        <FormField
          label={
            <SpaceBetween direction="horizontal" size="xs" alignItems="center">
              <span>Execution Region</span>
            </SpaceBetween>
          }
        >
          <Select
            selectedOption={findRegionOptions(state.formData.executionRegion)!}
            onChange={({ detail }) => handleFieldChange('executionRegion', detail.selectedOption.value!)}
            options={regionOptions}
          />
        </FormField>
        
        <FormField
          label={
            <SpaceBetween direction="horizontal" size="xs" alignItems="center">
              <span>User Journey</span>
              <Popover
                size="large"
                position="right"
                triggerType="custom"
                dismissButton={false}
                content={
                  <SpaceBetween direction="vertical" size="s">
                    <Box variant="strong">Tips:</Box>
                    <Box variant="small">• Be specific about UI elements (buttons, fields, links)</Box>
                    <Box variant="small">• Include expected outcomes and validations</Box>
                    <Box variant="small">• Use action words: click, enter, select, verify</Box>
                    <Box variant="strong">Example:</Box>
                    <Box variant="small">"User navigates to login page, enters email and password, clicks login button, and should be redirected to dashboard with welcome message displayed."</Box>
                  </SpaceBetween>
                }
              >
                <Button variant="inline-icon" iconName="status-info" />
              </Popover>
            </SpaceBetween>
          }
          errorText={state.validationErrors.userJourney}
        >
          <Textarea
            value={state.formData.userJourney}
            onChange={({ detail }) => handleFieldChange('userJourney', detail.value)}
            placeholder="Describe the complete user journey step by step..."
            rows={10}
            disabled={state.isGenerating}
            invalid={!!state.validationErrors.userJourney}
          />
        </FormField>

        <FormValidationSummary
          errors={state.validationErrors}
          warnings={state.validationWarnings}
          isFormValid={isFormValid()}
          showSuccessMessage={isFormValid() && Object.values(state.formData).some(value => value.trim())}
        />
        
        {state.isGenerating && (
          <LiveRegion>
            <Box
              margin={{ bottom: "xs", left: "l" }}
              color="text-body-secondary"
            >
              Generating a response
            </Box>
            <LoadingBar variant="gen-ai" />
          </LiveRegion>
        )}
        
        <SpaceBetween direction="horizontal" size="xs">
          <Button 
            variant="primary" 
            onClick={handleGenerateUsecase} 
            loading={state.isGenerating}
            disabled={state.isGenerating || !isFormValid()}
          >
            Generate Use Case
          </Button>
          <Button 
            onClick={() => navigate('/')} 
            disabled={state.isGenerating}
          >
            Cancel
          </Button>
        </SpaceBetween>
      </SpaceBetween>
    </Container>
  );
}