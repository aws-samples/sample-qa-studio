import { useState } from 'react';
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
import { wizardApi } from '../../../utils/api';
import { regionOptions, findRegionOptions } from '../../../utils/browser_regions';
import UsecasePreview from '../../UserJourneyWizard/UsecasePreview';

export default function DescribeAndGenerateStep({ state, dispatch, validationErrors }: StepProps) {
  const { userJourneyConfig, testPlatform, mobilePlatform, basicInfo } = state;
  const [error, setError] = useState<string | null>(null);

  const isMobile = testPlatform === 'mobile';
  const isAndroid = mobilePlatform === 'ANDROID';
  const isIOS = mobilePlatform === 'IOS';

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

    try {
      const request: any = {
        title: basicInfo.name.trim() || 'User Journey Use Case',
        starting_url: isMobile ? 'mobile://app' : basicInfo.startingUrl.trim(),
        userJourney: userJourneyConfig.userJourneyText.trim(),
        region: basicInfo.executionRegion,
      };

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
          label="User Journey"
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

        {/* Generate button */}
        <Button
          variant="primary"
          onClick={handleGenerate}
          loading={userJourneyConfig.isGenerating}
          disabled={
            userJourneyConfig.isGenerating ||
            !userJourneyConfig.userJourneyText.trim() ||
            (!isMobile && !basicInfo.startingUrl.trim())
          }
        >
          Generate
        </Button>
      </SpaceBetween>
    </Container>
  );
}
