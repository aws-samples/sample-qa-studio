import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Box from "@cloudscape-design/components/box";
import ColumnLayout from "@cloudscape-design/components/column-layout";
import Badge from "@cloudscape-design/components/badge";
import Alert from "@cloudscape-design/components/alert";
import FormField from "@cloudscape-design/components/form-field";
import Input from "@cloudscape-design/components/input";
import type { StepProps } from '../types';
import { api, exportImportApi } from '../../../utils/api';

// --- Label helpers ---

const METHOD_LABELS: Record<string, string> = {
  'blank': 'Blank',
  'interactive-wizard': 'Interactive Wizard',
  'template': 'Template',
  'user-journey': 'User Journey',
};

const PATH_LABELS: Record<string, string> = {
  'create-new': 'Create New',
  'clone': 'Clone',
  'import': 'Import',
};

// --- S3 upload helpers (mirrors CreateUsecase.tsx pattern) ---

async function uploadFileToS3(
  usecaseId: string,
  file: File,
  fileType: 'app_binary' | 'browser_policy',
  platform?: string | null
): Promise<boolean> {
  try {
    const payload: Record<string, any> = {
      fileType,
      usecaseId,
      filename: file.name,
    };
    if (platform) {
      payload.platform = platform;
    }
    const result = await api.post('generate-s3-url', payload);
    const contentType = fileType === 'browser_policy' ? 'application/json' : 'application/octet-stream';
    await fetch(result.signedUrl, {
      method: 'PUT',
      body: file,
      headers: { 'Content-Type': contentType },
    });
    return true;
  } catch (error) {
    console.error(`Failed to upload ${fileType}:`, error);
    return false;
  }
}

// --- Component ---

export default function ReviewAndCreateStep({ state, dispatch, validationErrors, submitTrigger }: StepProps) {
  const navigate = useNavigate();
  const [showSecretsForm, setShowSecretsForm] = useState(false);
  const [savingSecrets, setSavingSecrets] = useState(false);
  const [createdUsecaseId, setCreatedUsecaseId] = useState<string | null>(null);
  const initialTrigger = useRef(submitTrigger);

  // Watch submitTrigger from the wizard's Create button
  useEffect(() => {
    if (submitTrigger !== undefined && submitTrigger !== initialTrigger.current) {
      initialTrigger.current = submitTrigger;
      handleCreate();
    }
  }, [submitTrigger]); // eslint-disable-line react-hooks/exhaustive-deps

  const {
    creationPath,
    creationMethod,
    basicInfo,
    testPlatform,
    mobilePlatform,
    blankConfig,
    interactiveConfig,
    templateConfig,
    userJourneyConfig,
    cloneConfig,
    importConfig,
    isSubmitting,
    submitError,
  } = state;

  // --- Create handler ---

  const handleCreate = async () => {
    dispatch({ type: 'SUBMIT_START' });

    try {
      if (creationPath === 'create-new') {
        await handleCreateNew();
      } else if (creationPath === 'clone') {
        await handleClone();
      } else if (creationPath === 'import') {
        await handleImport();
      }
    } catch (error: any) {
      console.error('Creation failed:', error);
      dispatch({ type: 'SUBMIT_ERROR', payload: error.message || 'Failed to create use case. Please try again.' });
    }
  };

  const handleCreateNew = async () => {
    if (creationMethod === 'interactive-wizard') {
      // Session already created during recording — navigate to the usecase detail
      dispatch({ type: 'SUBMIT_SUCCESS' });
      if (interactiveConfig.usecaseId) {
        navigate(`/usecase/${interactiveConfig.usecaseId}`);
      } else {
        navigate('/');
      }
      return;
    }

    if (creationMethod === 'template') {
      // POST /templates/:id/apply
      const result = await api.post(`templates/${templateConfig.selectedTemplateId}/apply`, {
        name: basicInfo.name,
        description: basicInfo.description || templateConfig.description,
        tags: basicInfo.tags.split(',').map((t) => t.trim()).filter(Boolean),
        executing_region: basicInfo.executionRegion,
        model_id: basicInfo.modelId,
        starting_url: basicInfo.startingUrl,
      });
      dispatch({ type: 'SUBMIT_SUCCESS' });
      if (result?.usecaseId || result?.id) {
        navigate(`/usecase/${result.usecaseId || result.id}`);
      } else {
        navigate('/');
      }
      return;
    }

    if (creationMethod === 'user-journey') {
      // Import the generated usecase data
      if (userJourneyConfig.generatedUsecase) {
        const result = await exportImportApi.importUsecase(userJourneyConfig.generatedUsecase);
        dispatch({ type: 'SUBMIT_SUCCESS' });
        if (result?.usecaseId || result?.id) {
          navigate(`/usecase/${result.usecaseId || result.id}`);
        } else {
          navigate('/');
        }
      }
      return;
    }

    // Blank method: POST /usecases
    const payload: Record<string, any> = {
      name: basicInfo.name,
      description: basicInfo.description,
      active: basicInfo.active,
      enableCache: blankConfig.enableCache,
      executing_region: basicInfo.executionRegion,
      model_id: basicInfo.modelId,
      tags: basicInfo.tags.split(',').map((t) => t.trim()).filter(Boolean),
      test_platform: testPlatform,
    };

    if (testPlatform === 'mobile') {
      payload.platform = mobilePlatform;
      if (blankConfig.deviceArn) {
        payload.device_arn = blankConfig.deviceArn;
      }
      if (mobilePlatform === 'ANDROID') {
        payload.app_package = blankConfig.appPackage;
        payload.app_activity = blankConfig.appActivity;
      }
      if (mobilePlatform === 'IOS') {
        payload.bundle_id = blankConfig.bundleId;
      }
    } else {
      payload.starting_url = basicInfo.startingUrl;
    }

    const result = await api.post('usecase', payload);
    const usecaseId = result?.id;

    // Upload app binary if present (mobile)
    if (testPlatform === 'mobile' && blankConfig.appBinaryFile && usecaseId) {
      await uploadFileToS3(usecaseId, blankConfig.appBinaryFile, 'app_binary', mobilePlatform);
    }

    // Upload browser policy if present (web)
    if (testPlatform === 'web' && blankConfig.browserPolicyFile && usecaseId) {
      await uploadFileToS3(usecaseId, blankConfig.browserPolicyFile, 'browser_policy');
    }

    dispatch({ type: 'SUBMIT_SUCCESS' });
    if (usecaseId) {
      navigate(`/usecase/${usecaseId}`);
    } else {
      navigate('/');
    }
  };

  const handleClone = async () => {
    const result = await api.post(`usecase/${cloneConfig.selectedUsecaseId}/clone`, {
      name: cloneConfig.newName,
    });
    dispatch({ type: 'SUBMIT_SUCCESS' });
    if (result?.usecaseId) {
      navigate(`/usecase/${result.usecaseId}`);
    } else {
      navigate('/');
    }
  };

  const handleImport = async () => {
    if (!importConfig.file) return;

    const fileContent = await importConfig.file.text();
    const importData = JSON.parse(fileContent);
    const result = await exportImportApi.importUsecase(importData);

    if (result.success) {
      // Check for missing secrets
      if (result.missingSecrets && result.missingSecrets.length > 0) {
        setCreatedUsecaseId(result.usecaseId);
        // Initialize secret values from state
        const initialSecretValues: Record<string, string> = {};
        result.missingSecrets.forEach((secretKey: string) => {
          initialSecretValues[secretKey] = importConfig.secretValues[secretKey] || '';
        });
        dispatch({
          type: 'UPDATE_IMPORT_CONFIG',
          payload: {
            missingSecrets: result.missingSecrets,
            secretValues: initialSecretValues,
          },
        });
        dispatch({ type: 'SUBMIT_SUCCESS' });
        setShowSecretsForm(true);
        return;
      }

      dispatch({ type: 'SUBMIT_SUCCESS' });
      if (result.usecaseId || result.id) {
        navigate(`/usecase/${result.usecaseId || result.id}`);
      } else {
        navigate('/');
      }
    } else {
      throw new Error(result.message || 'Import failed');
    }
  };

  // --- Secrets handlers ---

  const handleSaveSecrets = async () => {
    if (!createdUsecaseId) return;
    setSavingSecrets(true);
    try {
      const secretsToSave = Object.entries(importConfig.secretValues)
        .filter(([, value]) => value.trim())
        .map(([key, value]) => ({ key, value: value.trim() }));

      if (secretsToSave.length > 0) {
        await api.post(`usecase/${createdUsecaseId}/secrets`, { secrets: secretsToSave });
      }
      navigate(`/usecase/${createdUsecaseId}`);
    } catch (error: any) {
      console.error('Failed to save secrets:', error);
      dispatch({ type: 'SUBMIT_ERROR', payload: error.message || 'Failed to save secrets' });
    } finally {
      setSavingSecrets(false);
    }
  };

  const handleSkipSecrets = () => {
    if (createdUsecaseId) {
      navigate(`/usecase/${createdUsecaseId}`);
    } else {
      navigate('/');
    }
  };

  // --- Secrets form (post-import) ---

  if (showSecretsForm) {
    return (
      <Container
        header={
          <Header variant="h2" description="Configure secret values for the imported use case">
            Configure secrets
          </Header>
        }
      >
        <SpaceBetween direction="vertical" size="l">
          <Alert type="info">
            The imported use case requires the following secrets. You can configure them now or skip and add them later.
          </Alert>

          {submitError && (
            <Alert type="error">{submitError}</Alert>
          )}

          {importConfig.missingSecrets.map((secretKey) => (
            <FormField key={secretKey} label={secretKey} description="Enter the secret value">
              <Input
                value={importConfig.secretValues[secretKey] || ''}
                onChange={({ detail }) =>
                  dispatch({
                    type: 'UPDATE_IMPORT_CONFIG',
                    payload: {
                      secretValues: { ...importConfig.secretValues, [secretKey]: detail.value },
                    },
                  })
                }
                type="password"
                placeholder="Enter secret value"
              />
            </FormField>
          ))}

          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="primary" onClick={handleSaveSecrets} loading={savingSecrets} disabled={savingSecrets}>
              Save secrets
            </Button>
            <Button onClick={handleSkipSecrets} disabled={savingSecrets}>
              Skip for now
            </Button>
          </SpaceBetween>
        </SpaceBetween>
      </Container>
    );
  }

  // --- Review summary rendering ---

  return (
    <SpaceBetween direction="vertical" size="l">
      {submitError && (
        <Alert type="error" dismissible onDismiss={() => dispatch({ type: 'SUBMIT_ERROR', payload: '' })}>
          {submitError}
        </Alert>
      )}

      {/* --- Create New paths --- */}
      {creationPath === 'create-new' && (
        <SpaceBetween direction="vertical" size="l">
          {/* Basic info */}
          <Container header={<Header variant="h3">Basic info</Header>}>
            <ColumnLayout columns={2} variant="text-grid">
              <div>
                <Box variant="awsui-key-label">Name</Box>
                <div>{basicInfo.name || '-'}</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Region</Box>
                <div>{basicInfo.executionRegion || '-'}</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Model</Box>
                <div>{basicInfo.modelId || '-'}</div>
              </div>
              {basicInfo.tags && (
                <div>
                  <Box variant="awsui-key-label">Tags</Box>
                  <SpaceBetween direction="horizontal" size="xs">
                    {basicInfo.tags.split(',').map((t) => t.trim()).filter(Boolean).map((tag) => (
                      <Badge key={tag}>{tag}</Badge>
                    ))}
                    {basicInfo.tags.split(',').filter((t) => t.trim()).length === 0 && <div>-</div>}
                  </SpaceBetween>
                </div>
              )}
              {basicInfo.description && (
                <div style={{ gridColumn: '1 / -1' }}>
                  <Box variant="awsui-key-label">Description</Box>
                  <div>{basicInfo.description}</div>
                </div>
              )}
            </ColumnLayout>
          </Container>

          {/* Platform */}
          <Container header={<Header variant="h3">Platform</Header>}>
            <ColumnLayout columns={2} variant="text-grid">
              <div>
                <Box variant="awsui-key-label">Test platform</Box>
                <div>{testPlatform === 'web' ? 'Web' : 'Mobile'}</div>
              </div>
              {testPlatform === 'mobile' && mobilePlatform && (
                <div>
                  <Box variant="awsui-key-label">Mobile platform</Box>
                  <div>{mobilePlatform}</div>
                </div>
              )}
            </ColumnLayout>
          </Container>

          {/* Method-specific config */}
          {creationMethod === 'blank' && <BlankReview state={state} />}
          {creationMethod === 'interactive-wizard' && <InteractiveWizardReview state={state} />}
          {creationMethod === 'template' && <TemplateReview state={state} />}
          {creationMethod === 'user-journey' && <UserJourneyReview state={state} />}
        </SpaceBetween>
      )}

      {/* --- Clone path --- */}
      {creationPath === 'clone' && <CloneReview state={state} />}

      {/* --- Import path --- */}
      {creationPath === 'import' && <ImportReview state={state} />}
    </SpaceBetween>
  );
}

// --- Sub-components for each review section ---

function BlankReview({ state }: { state: StepProps['state'] }) {
  const { testPlatform, mobilePlatform, blankConfig } = state;
  const isWeb = testPlatform === 'web';

  const items: { label: string; value: string }[] = [];

  if (isWeb) {
    items.push({ label: 'Starting URL', value: state.basicInfo.startingUrl || '-' });
  }
  if (!isWeb && mobilePlatform === 'ANDROID') {
    items.push({ label: 'App Package', value: blankConfig.appPackage || '-' });
    items.push({ label: 'App Activity', value: blankConfig.appActivity || '-' });
  }
  if (!isWeb && mobilePlatform === 'IOS') {
    items.push({ label: 'Bundle ID', value: blankConfig.bundleId || '-' });
  }
  if (!isWeb && blankConfig.deviceArn) {
    items.push({ label: 'Device', value: blankConfig.deviceArn });
  }
  items.push({ label: 'Active', value: state.basicInfo.active ? 'Yes' : 'No' });
  if (isWeb) {
    items.push({ label: 'Step caching (experimental)', value: blankConfig.enableCache ? 'Enabled' : 'Disabled' });
  }
  if (isWeb && blankConfig.browserPolicyFile) {
    items.push({ label: 'Browser policy', value: blankConfig.browserPolicyFile.name });
  }
  if (!isWeb && blankConfig.appBinaryFile) {
    items.push({ label: 'App binary', value: blankConfig.appBinaryFile.name });
  }

  return (
    <Container header={<Header variant="h3">{isWeb ? 'Browser configuration' : 'App configuration'}</Header>}>
      <ColumnLayout columns={2} variant="text-grid">
        {items.map((item) => (
          <div key={item.label}>
            <Box variant="awsui-key-label">{item.label}</Box>
            <div>{item.value}</div>
          </div>
        ))}
      </ColumnLayout>
    </Container>
  );
}

function InteractiveWizardReview({ state }: { state: StepProps['state'] }) {
  const { interactiveConfig } = state;

  return (
    <Container header={<Header variant="h3">Session summary</Header>}>
      <ColumnLayout columns={2} variant="text-grid">
        <div>
          <Box variant="awsui-key-label">Starting URL</Box>
          <div>{state.basicInfo.startingUrl || '-'}</div>
        </div>
        <div>
          <Box variant="awsui-key-label">Browser region</Box>
          <div>{interactiveConfig.browserRegion || '-'}</div>
        </div>
        <div>
          <Box variant="awsui-key-label">Steps recorded</Box>
          <div>{interactiveConfig.steps.length} step(s)</div>
        </div>
      </ColumnLayout>
    </Container>
  );
}

function TemplateReview({ state }: { state: StepProps['state'] }) {
  const { templateConfig } = state;
  const detail = templateConfig.templateDetail;

  if (!detail) {
    return (
      <Container header={<Header variant="h3">Template</Header>}>
        <Box>No template selected</Box>
      </Container>
    );
  }

  return (
    <Container header={<Header variant="h3">Template</Header>}>
      <ColumnLayout columns={2} variant="text-grid">
        <div>
          <Box variant="awsui-key-label">Template name</Box>
          <div>{detail.name}</div>
        </div>
        <div>
          <Box variant="awsui-key-label">Steps</Box>
          <div>{detail.steps?.length || 0} step(s)</div>
        </div>
        <div>
          <Box variant="awsui-key-label">Variables</Box>
          <div>{detail.variables?.length || 0} variable(s)</div>
        </div>
        {detail.tags && detail.tags.length > 0 && (
          <div>
            <Box variant="awsui-key-label">Tags</Box>
            <SpaceBetween direction="horizontal" size="xs">
              {detail.tags.filter((tag) => tag.toLowerCase() !== 'template').map((tag) => (
                <Badge key={tag}>{tag}</Badge>
              ))}
            </SpaceBetween>
          </div>
        )}
      </ColumnLayout>
    </Container>
  );
}

function UserJourneyReview({ state }: { state: StepProps['state'] }) {
  const { userJourneyConfig, testPlatform, mobilePlatform } = state;
  const isMobile = testPlatform === 'mobile';
  const generatedStepCount = userJourneyConfig.generatedUsecase?.steps?.length || 0;

  return (
    <Container header={<Header variant="h3">User journey</Header>}>
      <ColumnLayout columns={2} variant="text-grid">
        {!isMobile && (
          <div>
            <Box variant="awsui-key-label">Starting URL</Box>
            <div>{state.basicInfo.startingUrl || '-'}</div>
          </div>
        )}
        {isMobile && mobilePlatform === 'ANDROID' && (
          <>
            <div>
              <Box variant="awsui-key-label">App Package</Box>
              <div>{userJourneyConfig.appPackage || '-'}</div>
            </div>
            <div>
              <Box variant="awsui-key-label">App Activity</Box>
              <div>{userJourneyConfig.appActivity || '-'}</div>
            </div>
          </>
        )}
        {isMobile && mobilePlatform === 'IOS' && (
          <div>
            <Box variant="awsui-key-label">Bundle ID</Box>
            <div>{userJourneyConfig.bundleId || '-'}</div>
          </div>
        )}
        <div style={{ gridColumn: '1 / -1' }}>
          <Box variant="awsui-key-label">Description</Box>
          <div>{userJourneyConfig.userJourneyText || '-'}</div>
        </div>
        {userJourneyConfig.generatedUsecase && (
          <div>
            <Box variant="awsui-key-label">Generated steps</Box>
            <div>{generatedStepCount} step(s)</div>
          </div>
        )}
      </ColumnLayout>
    </Container>
  );
}

function CloneReview({ state }: { state: StepProps['state'] }) {
  const { cloneConfig } = state;
  const detail = cloneConfig.usecaseDetail;

  return (
    <SpaceBetween direction="vertical" size="l">
      <Container header={<Header variant="h3">Source use case</Header>}>
        {detail ? (
          <ColumnLayout columns={2} variant="text-grid">
            <div>
              <Box variant="awsui-key-label">Name</Box>
              <div>{detail.name}</div>
            </div>
            <div>
              <Box variant="awsui-key-label">Status</Box>
              <div>
                {detail.active ? (
                  <Badge color="green">Active</Badge>
                ) : (
                  <Badge color="red">Inactive</Badge>
                )}
              </div>
            </div>
            <div>
              <Box variant="awsui-key-label">Starting URL</Box>
              <div>{detail.starting_url || '-'}</div>
            </div>
            <div>
              <Box variant="awsui-key-label">Steps</Box>
              <div>{detail.steps?.length || 0} step(s)</div>
            </div>
            <div>
              <Box variant="awsui-key-label">Variables</Box>
              <div>{detail.variables?.length || 0} variable(s)</div>
            </div>
            <div>
              <Box variant="awsui-key-label">Headers</Box>
              <div>{Object.keys(detail.headers || {}).length} header(s)</div>
            </div>
            {detail.tags && detail.tags.length > 0 && (
              <div>
                <Box variant="awsui-key-label">Tags</Box>
                <SpaceBetween direction="horizontal" size="xs">
                  {detail.tags.map((tag) => (
                    <Badge key={tag}>{tag}</Badge>
                  ))}
                </SpaceBetween>
              </div>
            )}
            {detail.description && (
              <div style={{ gridColumn: '1 / -1' }}>
                <Box variant="awsui-key-label">Description</Box>
                <div>{detail.description}</div>
              </div>
            )}
          </ColumnLayout>
        ) : (
          <Box>No source use case selected</Box>
        )}
      </Container>

      <Container header={<Header variant="h3">Clone details</Header>}>
        <ColumnLayout columns={2} variant="text-grid">
          <div>
            <Box variant="awsui-key-label">New name</Box>
            <div>{cloneConfig.newName || '-'}</div>
          </div>
        </ColumnLayout>
      </Container>
    </SpaceBetween>
  );
}

function ImportReview({ state }: { state: StepProps['state'] }) {
  const { importConfig } = state;
  const parsed = importConfig.parsedData;

  if (!parsed) {
    return (
      <Container header={<Header variant="h3">Import summary</Header>}>
        <Box>No file uploaded</Box>
      </Container>
    );
  }

  return (
    <Container header={<Header variant="h3">Import summary</Header>}>
      <SpaceBetween direction="vertical" size="m">
        <ColumnLayout columns={2} variant="text-grid">
          <div>
            <Box variant="awsui-key-label">Name</Box>
            <div>{parsed.name || 'Unknown'}</div>
          </div>
          <div>
            <Box variant="awsui-key-label">Export version</Box>
            <div>{parsed.exportVersion}</div>
          </div>
          {parsed.region && (
            <div>
              <Box variant="awsui-key-label">Region</Box>
              <div>{parsed.region}</div>
            </div>
          )}
          {parsed.exportDate && (
            <div>
              <Box variant="awsui-key-label">Export date</Box>
              <div>{new Date(parsed.exportDate).toLocaleString()}</div>
            </div>
          )}
          <div>
            <Box variant="awsui-key-label">Steps</Box>
            <div>{parsed.stepCount} step(s)</div>
          </div>
          <div>
            <Box variant="awsui-key-label">Variables</Box>
            <div>{parsed.variableCount} variable(s)</div>
          </div>
          <div>
            <Box variant="awsui-key-label">Secrets</Box>
            <div>{parsed.secretCount} secret(s)</div>
          </div>
        </ColumnLayout>

        {importConfig.missingSecrets.length > 0 && (
          <Alert type="warning">
            <SpaceBetween direction="vertical" size="xs">
              <Box fontWeight="bold">Secrets configuration required</Box>
              <div>
                The following secrets will need to be configured after import:
              </div>
              <ul style={{ margin: '4px 0', paddingLeft: '20px' }}>
                {importConfig.missingSecrets.map((key) => (
                  <li key={key}>{key}</li>
                ))}
              </ul>
            </SpaceBetween>
          </Alert>
        )}
      </SpaceBetween>
    </Container>
  );
}
