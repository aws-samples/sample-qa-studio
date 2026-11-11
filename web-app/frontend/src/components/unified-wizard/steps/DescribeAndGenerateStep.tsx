import { useState, useEffect, useRef, useCallback } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import FormField from "@cloudscape-design/components/form-field";
import Input from "@cloudscape-design/components/input";
import Textarea from "@cloudscape-design/components/textarea";
import Select from "@cloudscape-design/components/select";
import Alert from "@cloudscape-design/components/alert";
import Box from "@cloudscape-design/components/box";
import LoadingBar from "@cloudscape-design/chat-components/loading-bar";
import type { StepProps } from '../types';
import { api, wizardApi, RecordingData } from '../../../utils/api';
import { regionOptions, findRegionOptions } from '../../../utils/browser_regions';
import UsecasePreview from '../../UserJourneyWizard/UsecasePreview';
import BrowserSessionPanel from '../../UserJourneyWizard/BrowserSessionPanel';
import RecordingSummary from '../../UserJourneyWizard/RecordingSummary';

interface BrowserSession {
  sessionId: string | null;
  usecaseId: string | null;
  status: 'idle' | 'starting' | 'active' | 'error';
  error: string | null;
}

const IDLE_SESSION: BrowserSession = { sessionId: null, usecaseId: null, status: 'idle', error: null };

async function terminateBrowserSession(sessionId: string, usecaseId: string) {
  try {
    await api.post(`wizard/${sessionId}/terminate/${usecaseId}`, {});
  } catch (err) {
    console.error('Failed to terminate browser session:', err);
  }
}

export default function DescribeAndGenerateStep({ state, dispatch, validationErrors }: StepProps) {
  const { userJourneyConfig, testPlatform, mobilePlatform, basicInfo } = state;
  const [error, setError] = useState<string | null>(null);
  const [browserSession, setBrowserSession] = useState<BrowserSession>(IDLE_SESSION);

  // The recording session is a live cloud browser: end it when the step
  // unmounts (wizard navigation) or the tab closes, so it never leaks.
  const sessionRef = useRef<{ sessionId: string; usecaseId: string } | null>(null);
  useEffect(() => {
    sessionRef.current = browserSession.sessionId && browserSession.usecaseId
      ? { sessionId: browserSession.sessionId, usecaseId: browserSession.usecaseId }
      : null;
  }, [browserSession.sessionId, browserSession.usecaseId]);
  useEffect(() => {
    const end = () => {
      if (sessionRef.current) {
        terminateBrowserSession(sessionRef.current.sessionId, sessionRef.current.usecaseId);
        sessionRef.current = null;
      }
    };
    window.addEventListener('beforeunload', end);
    return () => {
      window.removeEventListener('beforeunload', end);
      end();
    };
  }, []);

  const isMobile = testPlatform === 'mobile';
  const isElectron = testPlatform === 'electron';
  const isWeb = !isMobile && !isElectron;
  const isAndroid = mobilePlatform === 'ANDROID';
  const isIOS = mobilePlatform === 'IOS';

  const endBrowserSession = useCallback(async () => {
    const current = sessionRef.current;
    sessionRef.current = null;
    setBrowserSession(IDLE_SESSION);
    if (current) {
      await terminateBrowserSession(current.sessionId, current.usecaseId);
    }
  }, []);

  const handleStartBrowserSession = async () => {
    setBrowserSession({ ...IDLE_SESSION, status: 'starting' });
    try {
      const response = await api.post('wizard/start', {
        application_id: basicInfo.applicationId,
        name: basicInfo.name.trim() || 'User Journey Recording',
        description: 'Browser recording session for user journey',
        starting_url: basicInfo.startingUrl.trim(),
        tags: [],
        executing_region: basicInfo.executionRegion,
      });
      if (!response?.sessionId || !response?.usecaseId) {
        throw new Error('Invalid response from server: missing sessionId or usecaseId');
      }
      setBrowserSession({ sessionId: response.sessionId, usecaseId: response.usecaseId, status: 'active', error: null });
    } catch (err: any) {
      console.error('Failed to start browser session:', err);
      setBrowserSession({
        ...IDLE_SESSION,
        status: 'error',
        error: err.message || 'Failed to start browser session. Please try again.',
      });
    }
  };

  const handleRecordingComplete = useCallback((recordingData: RecordingData) => {
    dispatch({ type: 'UPDATE_USER_JOURNEY_CONFIG', payload: { recordingData } });
  }, [dispatch]);

  const handleFieldChange = (field: string, value: string) => {
    dispatch({
      type: 'UPDATE_USER_JOURNEY_CONFIG',
      payload: { [field]: value },
    });
  };

  const handleGenerate = async () => {
    setError(null);

    dispatch({
      type: 'UPDATE_USER_JOURNEY_CONFIG',
      payload: { isGenerating: true },
    });

    // The recording is complete once it is in state; free the live browser.
    await endBrowserSession();

    try {
      const request: any = {
        title: basicInfo.name.trim() || 'User Journey Use Case',
        // The generator needs a URL-shaped hint; app platforms have no real URL.
        starting_url: isMobile ? 'mobile://app' : isElectron ? 'electron://app' : basicInfo.startingUrl.trim(),
        userJourney: userJourneyConfig.userJourneyText.trim(),
        executing_region: basicInfo.executionRegion,
      };
      if (isWeb && userJourneyConfig.recordingData) {
        request.recording_data = userJourneyConfig.recordingData;
      }

      const response = await wizardApi.generateUsecase(request);

      if (response.success) {
        const usecaseData = JSON.parse(response.usecaseData);

        // Merge mobile platform fields if applicable
        if (isMobile) {
          usecaseData.usecase = {
            ...usecaseData.usecase,
            test_platform: 'mobile',
            platform: mobilePlatform || '',
            ...(isAndroid ? { app_package: userJourneyConfig.appPackage, app_activity: userJourneyConfig.appActivity } : {}),
            ...(isIOS ? { bundle_id: userJourneyConfig.bundleId } : {}),
            starting_url: '',
          };
        } else if (isElectron) {
          usecaseData.usecase = {
            ...usecaseData.usecase,
            test_platform: 'electron',
            ...(userJourneyConfig.bundleId.trim() ? { bundle_id: userJourneyConfig.bundleId.trim() } : {}),
            starting_url: '',
          };
        }

        dispatch({
          type: 'UPDATE_USER_JOURNEY_CONFIG',
          payload: {
            isGenerating: false,
            generatedUsecase: usecaseData,
            previewMode: true,
          },
        });
      } else {
        throw new Error(response.error || 'Failed to generate use case');
      }
    } catch (err: any) {
      console.error('Failed to generate use case:', err);
      setError(err.message || 'Failed to generate use case. Please try again.');
      dispatch({
        type: 'UPDATE_USER_JOURNEY_CONFIG',
        payload: { isGenerating: false },
      });
    }
  };

  const handleRegenerate = () => {
    dispatch({
      type: 'UPDATE_USER_JOURNEY_CONFIG',
      payload: {
        generatedUsecase: null,
        previewMode: false,
      },
    });
    setError(null);
  };

  // No-op for import — in the unified wizard, import happens at the Review step
  const handleImportNoop = () => {
    // Import is handled by ReviewAndCreateStep
  };

  const regions = regionOptions();

  // If preview mode with generated usecase, show the preview
  if (userJourneyConfig.previewMode && userJourneyConfig.generatedUsecase) {
    return (
      <SpaceBetween direction="vertical" size="l">
        <Container header={<Header variant="h2">Generated use case preview</Header>}>
          <SpaceBetween direction="vertical" size="m">
            <Alert type="success">
              Use case generated successfully. Review the preview below, then click "Next" to proceed
              to the review step, or "Regenerate" to try again.
            </Alert>
            <Box>
              <Button onClick={handleRegenerate}>Regenerate</Button>
            </Box>
          </SpaceBetween>
        </Container>

        <UsecasePreview
          usecase={userJourneyConfig.generatedUsecase}
          onImport={handleImportNoop}
          onRegenerate={handleRegenerate}
          isImporting={false}
        />
      </SpaceBetween>
    );
  }

  // Default: describe form
  return (
    <Container>
      <SpaceBetween direction="vertical" size="l">
        {error && (
          <Alert
            type="error"
            dismissible
            onDismiss={() => setError(null)}
            action={<Button onClick={handleGenerate}>Retry</Button>}
          >
            {error}
          </Alert>
        )}

        {userJourneyConfig.isGenerating && (
          <Box padding={{ vertical: 's' }}>
            <SpaceBetween direction="vertical" size="s">
              <Box variant="small" color="text-body-secondary">
                Generating use case with AI... This may take a moment.
              </Box>
              <LoadingBar variant="gen-ai" />
            </SpaceBetween>
          </Box>
        )}

        {/* Mobile-specific fields */}
        {isMobile && isAndroid && (
          <SpaceBetween direction="vertical" size="l">
            <FormField
              label="App Package"
              description="e.g. com.example.myapp"
              errorText={validationErrors.appPackage}
            >
              <Input
                value={userJourneyConfig.appPackage}
                onChange={({ detail }) => handleFieldChange('appPackage', detail.value)}
                placeholder="com.example.myapp"
                disabled={userJourneyConfig.isGenerating}
              />
            </FormField>
            <FormField
              label="App Activity"
              description="e.g. com.example.myapp.MainActivity"
              errorText={validationErrors.appActivity}
            >
              <Input
                value={userJourneyConfig.appActivity}
                onChange={({ detail }) => handleFieldChange('appActivity', detail.value)}
                placeholder="com.example.myapp.MainActivity"
                disabled={userJourneyConfig.isGenerating}
              />
            </FormField>
          </SpaceBetween>
        )}

        {isElectron && (
          <FormField
            label="Bundle ID"
            description="Optional. The desktop app's CFBundleIdentifier, verified by the runner against the launched .app."
            errorText={validationErrors.bundleId}
          >
            <Input
              value={userJourneyConfig.bundleId}
              onChange={({ detail }) => handleFieldChange('bundleId', detail.value)}
              placeholder="com.example.desktop"
              disabled={userJourneyConfig.isGenerating}
            />
          </FormField>
        )}

        {isMobile && isIOS && (
          <FormField
            label="Bundle ID"
            description="e.g. com.example.myapp"
            errorText={validationErrors.bundleId}
          >
            <Input
              value={userJourneyConfig.bundleId}
              onChange={({ detail }) => handleFieldChange('bundleId', detail.value)}
              placeholder="com.example.myapp"
              disabled={userJourneyConfig.isGenerating}
            />
          </FormField>
        )}

        {/* User Journey description */}
        <FormField
          label={`User Journey${userJourneyConfig.recordingData ? ' (optional — recording provided)' : ''}`}
          description="Describe the complete user journey step by step. Be specific about UI elements, actions, and expected outcomes."
          errorText={validationErrors.userJourneyText}
        >
          <Textarea
            value={userJourneyConfig.userJourneyText}
            onChange={({ detail }) => handleFieldChange('userJourneyText', detail.value)}
            placeholder="Describe the complete user journey step by step..."
            rows={8}
            disabled={userJourneyConfig.isGenerating}
          />
        </FormField>

        {/* Optional browser recording (web): extra context for the generator */}
        {isWeb && browserSession.status === 'error' && browserSession.error && (
          <Alert
            type="error"
            dismissible
            onDismiss={() => setBrowserSession(IDLE_SESSION)}
            action={<Button onClick={handleStartBrowserSession}>Retry</Button>}
          >
            {browserSession.error}
          </Alert>
        )}
        {isWeb && browserSession.status === 'active' && browserSession.sessionId && browserSession.usecaseId ? (
          <BrowserSessionPanel
            sessionId={browserSession.sessionId}
            usecaseId={browserSession.usecaseId}
            onSessionEnd={endBrowserSession}
            onRecordingComplete={handleRecordingComplete}
          />
        ) : isWeb && (
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
            <Button
              onClick={handleStartBrowserSession}
              loading={browserSession.status === 'starting'}
              disabled={userJourneyConfig.isGenerating || !basicInfo.startingUrl.trim() || browserSession.status === 'starting'}
              iconName="external"
            >
              Start Browser Session
            </Button>
          </Container>
        )}
        {userJourneyConfig.recordingData && (
          <RecordingSummary recordingData={userJourneyConfig.recordingData} />
        )}

        {/* Generate button */}
        <Button
          variant="primary"
          onClick={handleGenerate}
          loading={userJourneyConfig.isGenerating}
          disabled={
            userJourneyConfig.isGenerating ||
            (!userJourneyConfig.userJourneyText.trim() && !userJourneyConfig.recordingData) ||
            (isWeb && !basicInfo.startingUrl.trim())
          }
        >
          Generate
        </Button>
      </SpaceBetween>
    </Container>
  );
}
