import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Box from "@cloudscape-design/components/box";
import Alert from "@cloudscape-design/components/alert";
import BreadcrumbGroup from "@cloudscape-design/components/breadcrumb-group";
import { wizardApi, exportImportApi, api, RecordingData } from '../utils/api';
import { ErrorState, errorManager } from '../utils/errorManager';
import { useRetry } from '../utils/retryManager';
import { validationManager, WIZARD_FIELD_CONFIGS } from '../utils/validation';
import ErrorDisplay from './common/ErrorDisplay';
import FormValidationSummary from './common/FormValidationSummary';
import FormField from "@cloudscape-design/components/form-field";
import Input from "@cloudscape-design/components/input";
import Textarea from "@cloudscape-design/components/textarea";
import UsecasePreview from './UserJourneyWizard/UsecasePreview';
import BrowserSessionPanel from './UserJourneyWizard/BrowserSessionPanel';
import RecordingSummary from './UserJourneyWizard/RecordingSummary';
import Popover from "@cloudscape-design/components/popover";
import LoadingBar from "@cloudscape-design/chat-components/loading-bar";
import Select, { SelectProps } from "@cloudscape-design/components/select";
import LiveRegion from "@cloudscape-design/components/live-region";
import { regionOptions, findRegionOptions } from './../utils/browser_regions'
import RadioGroup from "@cloudscape-design/components/radio-group";

const platformOptions: SelectProps.Options = [
  { label: 'Android', value: 'ANDROID' },
  { label: 'iOS', value: 'IOS' },
];

declare const __APP_CONFIG__: { defaultRegion: string; enabledRegions: string[]; apiEndpoint: string; baseName: string; version: string };

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
  browserSession: {
    sessionId: string | null;
    usecaseId: string | null;
    status: 'idle' | 'starting' | 'active' | 'error';
    error: string | null;
  };
  recording: {
    status: 'idle' | 'starting' | 'recording' | 'stopping' | 'completed' | 'error';
    data: RecordingData | null;
    error: string | null;
  };
}

export default function UserJourneyWizard({ onUsecaseCreated }: UserJourneyWizardProps) {
  const navigate = useNavigate();
  const { executeWithRetry } = useRetry();
  const [state, setState] = useState<WizardState>({
    formData: {
      title: '',
      startingUrl: '',
      userJourney: '',
      executionRegion: __APP_CONFIG__.defaultRegion
    },
    isGenerating: false,
    isImporting: false,
    generatedUsecase: null,
    previewMode: false,
    error: null,
    validationErrors: {},
    validationWarnings: {},
    importSuccess: null,
    browserSession: {
      sessionId: null,
      usecaseId: null,
      status: 'idle',
      error: null,
    },
    recording: {
      status: 'idle',
      data: null,
      error: null,
    },
  });

  // Mobile platform state (from current branch)
  const [testPlatform, setTestPlatform] = useState<string>('web');
  const [mobilePlatform, setMobilePlatform] = useState<SelectProps.Option | null>(null);
  const [appPackage, setAppPackage] = useState('');
  const [appActivity, setAppActivity] = useState('');
  const [bundleId, setBundleId] = useState('');

  const isMobile = testPlatform === 'mobile';
  const isAndroid = mobilePlatform?.value === 'ANDROID';
  const isIOS = mobilePlatform?.value === 'IOS';

  // Ref to track session for cleanup in beforeunload / unmount
  const sessionRef = useRef<{ sessionId: string; usecaseId: string } | null>(null);
  // Ref to track recording status for beforeunload (can't read state in event handler)
  const recordingStatusRef = useRef(state.recording.status);

  // Keep refs in sync with state
  useEffect(() => {
    if (state.browserSession.sessionId && state.browserSession.usecaseId) {
      sessionRef.current = {
        sessionId: state.browserSession.sessionId,
        usecaseId: state.browserSession.usecaseId,
      };
    } else {
      sessionRef.current = null;
    }
  }, [state.browserSession.sessionId, state.browserSession.usecaseId]);

  useEffect(() => {
    recordingStatusRef.current = state.recording.status;
  }, [state.recording.status]);

  const terminateBrowserSession = useCallback(async (sessionId: string, usecaseId: string) => {
    try {
      await api.post(`wizard/${sessionId}/terminate/${usecaseId}`, {});
    } catch (err) {
      console.error('Failed to terminate browser session:', err);
    }
  }, []);

  // Stop recording before terminating session, if recording is active
  const stopRecordingBeforeTerminate = useCallback(async (sessionId: string) => {
    try {
      await wizardApi.sendRecordingCommand(sessionId, 'recording_stop');
    } catch (err) {
      console.error('Failed to stop recording before session end:', err);
    }
  }, []);

  // Cleanup on component unmount and beforeunload to terminate session on tab/window close
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (sessionRef.current) {
        const { sessionId, usecaseId } = sessionRef.current;
        if (recordingStatusRef.current === 'recording' || recordingStatusRef.current === 'starting') {
          stopRecordingBeforeTerminate(sessionId);
        }
        terminateBrowserSession(sessionId, usecaseId);
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      // Terminate on unmount (navigation away)
      if (sessionRef.current) {
        const { sessionId, usecaseId } = sessionRef.current;
        if (recordingStatusRef.current === 'recording' || recordingStatusRef.current === 'starting') {
          stopRecordingBeforeTerminate(sessionId);
        }
        terminateBrowserSession(sessionId, usecaseId);
      }
    };
  }, [terminateBrowserSession, stopRecordingBeforeTerminate]);

  const isValidHttpUrl = (urlString: string): boolean => {
    try {
      const url = new URL(urlString);
      return url.protocol === 'http:' || url.protocol === 'https:';
    } catch {
      return false;
    }
  };

  const handleStartBrowserSession = async () => {
    if (!isValidHttpUrl(state.formData.startingUrl)) {
      setState(prev => ({
        ...prev,
        validationErrors: {
          ...prev.validationErrors,
          startingUrl: 'Please enter a valid URL (http:// or https://)',
        },
      }));
      return;
    }

    setState(prev => ({
      ...prev,
      browserSession: { ...prev.browserSession, status: 'starting', error: null },
    }));

    try {
      const response = await api.post('wizard/start', {
        name: state.formData.title.trim() || 'User Journey Recording',
        description: 'Browser recording session for user journey',
        starting_url: state.formData.startingUrl.trim(),
        tags: [],
        region: state.formData.executionRegion,
      });

      if (!response?.sessionId || !response?.usecaseId) {
        throw new Error('Invalid response from server: missing sessionId or usecaseId');
      }

      setState(prev => ({
        ...prev,
        browserSession: {
          sessionId: response.sessionId,
          usecaseId: response.usecaseId,
          status: 'active',
          error: null,
        },
      }));
    } catch (err: any) {
      console.error('Failed to start browser session:', err);
      setState(prev => ({
        ...prev,
        browserSession: {
          ...prev.browserSession,
          status: 'error',
          error: err.message || 'Failed to start browser session. Please try again.',
        },
      }));
    }
  };

  const handleSessionEnd = useCallback(async () => {
    const { sessionId, usecaseId } = state.browserSession;
    if (sessionId && usecaseId) {
      if (state.recording.status === 'recording' || state.recording.status === 'starting') {
        await stopRecordingBeforeTerminate(sessionId);
      }
      await terminateBrowserSession(sessionId, usecaseId);
    }
    setState(prev => ({
      ...prev,
      browserSession: { sessionId: null, usecaseId: null, status: 'idle', error: null },
    }));
  }, [state.browserSession.sessionId, state.browserSession.usecaseId, state.recording.status, terminateBrowserSession, stopRecordingBeforeTerminate]);

  const handleRecordingComplete = useCallback((data: RecordingData) => {
    setState(prev => ({
      ...prev,
      recording: { status: 'completed', data, error: null },
    }));
  }, []);

  const validateForm = (): boolean => {
    const hasRecording = !!state.recording.data;

    // When recording data is available, user journey text is optional
    const configs = hasRecording
      ? {
        ...WIZARD_FIELD_CONFIGS,
        userJourney: {
          ...WIZARD_FIELD_CONFIGS.userJourney,
          rules: { ...WIZARD_FIELD_CONFIGS.userJourney.rules, required: false, minLength: undefined },
        },
      }
      : WIZARD_FIELD_CONFIGS;

    const validation = validationManager.validateForm(state.formData, configs);

    // If user journey is provided (even with recording), still validate min length
    if (hasRecording && state.formData.userJourney.trim().length > 0 && state.formData.userJourney.trim().length < 50) {
      validation.errors.userJourney = 'User journey description must be at least 50 characters if provided';
      validation.isValid = false;
    }

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
      validationErrors: { ...prev.validationErrors, [field]: '' },
      validationWarnings: { ...prev.validationWarnings, [field]: '' }
    }));
  };

  const handleGenerateUsecase = async (previousError?: ErrorState | null) => {
    if (!validateForm()) {
      return;
    }

    setState(prev => ({ ...prev, isGenerating: true, error: null }));

    // Terminate browser session first if active
    if (state.browserSession.sessionId && state.browserSession.usecaseId) {
      if (state.recording.status === 'recording' || state.recording.status === 'starting') {
        await stopRecordingBeforeTerminate(state.browserSession.sessionId);
      }
      await terminateBrowserSession(state.browserSession.sessionId, state.browserSession.usecaseId);
      setState(prev => ({
        ...prev,
        browserSession: { sessionId: null, usecaseId: null, status: 'idle', error: null },
      }));
    }

    try {
      const request: any = {
        title: state.formData.title,
        starting_url: state.formData.startingUrl,
        userJourney: state.formData.userJourney,
        region: state.formData.executionRegion,
      };

      // Include recording_data when available
      if (state.recording.data) {
        request.recording_data = state.recording.data;
      }

      const response = await wizardApi.generateUsecase(request);

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

      const errorState = (error as ErrorState).type
        ? error as ErrorState
        : errorManager.createError('unknown',
          'An unexpected error occurred while generating the use case');

      if (previousError) {
        errorState.retryCount = previousError.retryCount;
        errorState.maxRetries = previousError.maxRetries;
      }

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

    // Merge mobile platform fields into the generated usecase
    const usecaseToImport = { ...state.generatedUsecase };
    if (isMobile) {
      usecaseToImport.usecase = {
        ...usecaseToImport.usecase,
        test_platform: 'mobile',
        platform: mobilePlatform?.value || '',
        ...(isAndroid ? { app_package: appPackage, app_activity: appActivity } : {}),
        ...(isIOS ? { bundle_id: bundleId } : {}),
        starting_url: '',
      };
    }

    const result = await executeWithRetry(
      () => exportImportApi.importUsecase(usecaseToImport),
      { maxRetries: 2 }
    );

    if (result.success) {
      const response = result.data;

      if (response.success) {
        const usecaseId = response.usecaseId;

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
          setState(prev => ({
            ...prev,
            formData: { title: '', startingUrl: '', userJourney: '', executionRegion: __APP_CONFIG__.defaultRegion },
            generatedUsecase: null,
            previewMode: false,
            isImporting: false,
            isGenerating: false,
            validationErrors: {},
            validationWarnings: {},
            importSuccess: null
          }));

          if (onUsecaseCreated) {
            onUsecaseCreated(usecaseId);
          }

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
    const updatedError = state.error ? errorManager.incrementRetryCount(state.error) : null;
    setState(prev => ({ ...prev, error: updatedError }));

    if (state.previewMode) {
      handleImportUsecase();
    } else {
      handleGenerateUsecase(updatedError);
    }
  };

  const handleDismissError = () => {
    setState(prev => ({ ...prev, error: null }));
  };

  const isFormValid = () => {
    if (Object.keys(state.validationErrors).some(key => state.validationErrors[key])) {
      return false;
    }

    const hasRecording = !!state.recording.data;

    return Object.keys(WIZARD_FIELD_CONFIGS).every(field => {
      const config = WIZARD_FIELD_CONFIGS[field];
      const value = state.formData[field as keyof typeof state.formData];

      if (field === 'userJourney' && hasRecording) {
        return true;
      }

      if (config.rules.required) {
        return value && value.trim().length > 0;
      }

      return true;
    });
  };

  if (state.previewMode && state.generatedUsecase) {
    return (
      <SpaceBetween direction="vertical" size="l">
        <BreadcrumbGroup
          items={[
            { text: 'Home', href: '/' },
            { text: 'Create Use Case', href: '/create' },
            { text: 'Create from User Journey', href: '/create/journey' }
          ]}
          onFollow={(event) => {
            event.preventDefault();
            navigate(event.detail.href);
          }}
        />

        <Header variant="h1">User Journey Wizard - Preview</Header>

        <Container>
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
      </SpaceBetween>
    );
  }

  const isBrowserSessionActive = state.browserSession.status === 'active'
    && !!state.browserSession.sessionId
    && !!state.browserSession.usecaseId;

  const renderFormFields = () => (
    <>
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

      {/* Platform selector */}
      <FormField label="Test platform">
        <RadioGroup
          value={testPlatform}
          onChange={({ detail }) => {
            setTestPlatform(detail.value);
            setMobilePlatform(null);
          }}
          items={[
            { value: 'web', label: 'Web' },
            { value: 'mobile', label: 'Mobile' },
          ]}
        />
      </FormField>

      {isMobile && (
        <SpaceBetween direction="vertical" size="l">
          <Alert type="warning">
            Mobile testing is still experimental. Features may change or behave unexpectedly.
          </Alert>
          <Alert type="info">
            Device Farm operations run in us-west-2. You can upload the app binary after the use case is created.
          </Alert>
          <FormField label="Mobile platform">
            <Select
              selectedOption={mobilePlatform}
              onChange={({ detail }) => setMobilePlatform(detail.selectedOption)}
              options={platformOptions}
              placeholder="Select platform"
            />
          </FormField>
          {isAndroid && (
            <>
              <FormField label="App package" description="e.g. com.example.myapp">
                <Input value={appPackage} onChange={({ detail }) => setAppPackage(detail.value)} placeholder="com.example.myapp" />
              </FormField>
              <FormField label="App activity" description="e.g. com.example.myapp.MainActivity">
                <Input value={appActivity} onChange={({ detail }) => setAppActivity(detail.value)} placeholder="com.example.myapp.MainActivity" />
              </FormField>
            </>
          )}
          {isIOS && (
            <FormField label="Bundle ID" description="e.g. com.example.myapp">
              <Input value={bundleId} onChange={({ detail }) => setBundleId(detail.value)} placeholder="com.example.myapp" />
            </FormField>
          )}
        </SpaceBetween>
      )}

      {!isMobile && (
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
            disabled={state.isGenerating || isBrowserSessionActive}
            invalid={!!state.validationErrors.startingUrl}
          />
        </FormField>
      )}

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
          options={regionOptions()}
          disabled={isBrowserSessionActive}
        />
      </FormField>

      <FormField
        label={
          <SpaceBetween direction="horizontal" size="xs" alignItems="center">
            <span>User Journey{state.recording.data ? ' (optional — recording provided)' : ''}</span>
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

      {/* Browser session section — only for web platform, below the form fields */}
      {!isMobile && !isBrowserSessionActive && (
        <Box padding={{ top: "l" }}>
          <Container
            header={
              <Header
                variant="h3"
                description="Optionally record your interactions in a live browser to help the AI generate more accurate test steps."
              >
                Enhance with browser recording
              </Header>
            }
          >
            <SpaceBetween direction="vertical" size="m">
              <Box variant="p" color="text-body-secondary" fontSize="body-s">
                You can skip this step and generate a use case from the text description above.
                If you'd like more precise results, start a browser session to interact with your
                application. Your recorded clicks, inputs, and navigation will be included as
                additional context for the AI.
              </Box>
              <Box>
                <Button
                  onClick={handleStartBrowserSession}
                  loading={state.browserSession.status === 'starting'}
                  disabled={state.isGenerating || !state.formData.startingUrl.trim() || state.browserSession.status === 'starting'}
                  iconName="external"
                >
                  Start Browser Session
                </Button>
              </Box>
            </SpaceBetween>
          </Container>
        </Box>
      )}
    </>
  );

  return (
    <SpaceBetween direction="vertical" size="l">
      <BreadcrumbGroup
        items={[
          { text: 'Home', href: '/' },
          { text: 'Create Use Case', href: '/create' },
          { text: 'Create from User Journey', href: '/create/journey' }
        ]}
        onFollow={(event) => {
          event.preventDefault();
          navigate(event.detail.href);
        }}
      />

      <Header
        variant="h1"
        description="Create automated test use cases by describing your user journey in natural language"
      >
        Create from User Journey
      </Header>

      <Container>
        <SpaceBetween direction="vertical" size="l">
          {state.error && (
            <ErrorDisplay
              error={state.error}
              onRetry={handleRetry}
              onDismiss={handleDismissError}
              isRetrying={state.isGenerating || state.isImporting}
            />
          )}

          {/* Browser session error */}
          {state.browserSession.status === 'error' && state.browserSession.error && (
            <Alert
              type="error"
              dismissible
              onDismiss={() => setState(prev => ({
                ...prev,
                browserSession: { ...prev.browserSession, status: 'idle', error: null },
              }))}
              action={
                <Button onClick={handleStartBrowserSession}>Retry</Button>
              }
            >
              {state.browserSession.error}
            </Alert>
          )}

          {/* Form fields always render full-width on top */}
          <SpaceBetween direction="vertical" size="l">
            {renderFormFields()}
          </SpaceBetween>

          {/* Browser session panel renders below the form when active (web only) */}
          {!isMobile && isBrowserSessionActive && (
            <BrowserSessionPanel
              sessionId={state.browserSession.sessionId!}
              usecaseId={state.browserSession.usecaseId!}
              onSessionEnd={handleSessionEnd}
              onRecordingComplete={handleRecordingComplete}
            />
          )}

          <FormValidationSummary
            errors={state.validationErrors}
            warnings={state.validationWarnings}
            isFormValid={isFormValid()}
            showSuccessMessage={isFormValid() && Object.values(state.formData).some(value => value.trim())}
          />

          {/* Recording summary near Generate button when recording data is available */}
          {state.recording.data && (
            <RecordingSummary recordingData={state.recording.data} />
          )}

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
              onClick={() => handleGenerateUsecase()}
              loading={state.isGenerating}
              disabled={state.isGenerating || !isFormValid()}
            >
              Generate Use Case
            </Button>
            <Button
              onClick={() => navigate('/create')}
              disabled={state.isGenerating}
            >
              Cancel
            </Button>
          </SpaceBetween>
        </SpaceBetween>
      </Container>
    </SpaceBetween>
  );
}
