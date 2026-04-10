import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import FormField from "@cloudscape-design/components/form-field";
import Input from "@cloudscape-design/components/input";
import Textarea from "@cloudscape-design/components/textarea";
import Checkbox from "@cloudscape-design/components/checkbox";
import Toggle from "@cloudscape-design/components/toggle";
import Select, {SelectProps} from "@cloudscape-design/components/select";
import RadioGroup from "@cloudscape-design/components/radio-group";
import Alert from "@cloudscape-design/components/alert";
import FileUpload from "@cloudscape-design/components/file-upload";
import StatusIndicator from "@cloudscape-design/components/status-indicator";
import BreadcrumbGroup from "@cloudscape-design/components/breadcrumb-group";
import { api } from '../utils/api';
import { devicesApi, DeviceFarmDevice } from '../utils/api';
import { regionOptions, findRegionOptions } from '../utils/browser_regions';
import { useModels } from '../hooks/useModels';

const platformOptions: SelectProps.Options = [
  { label: 'Android', value: 'ANDROID' },
  { label: 'iOS', value: 'IOS' },
];

export default function CreateUsecase() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [starting_url, setStartingUrl] = useState('');
  const [active, setActive] = useState(true);
  const [enableCache, setEnableCache] = useState(false);
  const [tags, setTags] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedRegion, setSelectedRegion] = useState(findRegionOptions() as SelectProps.Option);
  const { modelOptions, findModelOption, loading: modelsLoading } = useModels();
  const [selectedModel, setSelectedModel] = useState<SelectProps.Option | null>(null);

  // Mobile-specific state
  const [testPlatform, setTestPlatform] = useState<string>('web');
  const [mobilePlatform, setMobilePlatform] = useState<SelectProps.Option | null>(null);
  const [appPackage, setAppPackage] = useState('');
  const [appActivity, setAppActivity] = useState('');
  const [bundleId, setBundleId] = useState('');
  const [appBinaryFiles, setAppBinaryFiles] = useState<File[]>([]);
  const [uploadStatus, setUploadStatus] = useState<'none' | 'uploading' | 'success' | 'error'>('none');
  const [uploadError, setUploadError] = useState('');
  const [deviceOptions, setDeviceOptions] = useState<SelectProps.Options>([]);
  const [selectedDevice, setSelectedDevice] = useState<SelectProps.Option | null>(null);
  const [devicesLoading, setDevicesLoading] = useState(false);

  // Browser policy state
  const [policyFiles, setPolicyFiles] = useState<File[]>([]);
  const [policyUploadStatus, setPolicyUploadStatus] = useState<'none' | 'uploading' | 'success' | 'error'>('none');
  const [policyUploadError, setPolicyUploadError] = useState('');

  // Set default model once models are loaded
  React.useEffect(() => {
    if (!modelsLoading && !selectedModel) {
      setSelectedModel(findModelOption());
    }
  }, [modelsLoading, selectedModel, findModelOption]);

  const isMobile = testPlatform === 'mobile';
  const isAndroid = mobilePlatform?.value === 'ANDROID';
  const isIOS = mobilePlatform?.value === 'IOS';

  // Fetch Device Farm devices when mobile platform changes
  React.useEffect(() => {
    if (!isMobile || !mobilePlatform?.value) {
      setDeviceOptions([]);
      setSelectedDevice(null);
      return;
    }
    let cancelled = false;
    setDevicesLoading(true);
    devicesApi.list(mobilePlatform.value).then(data => {
      if (cancelled) return;
      const options = data.devices.map(d => ({
        label: `${d.name} (${d.os})`,
        value: d.arn,
        description: `${d.manufacturer} · ${d.formFactor} · ${d.availability === 'HIGHLY_AVAILABLE' ? 'Highly available' : d.availability}`,
      }));
      setDeviceOptions(options);
      setSelectedDevice(null);
    }).catch(err => {
      if (!cancelled) console.error('Failed to load devices:', err);
    }).finally(() => {
      if (!cancelled) setDevicesLoading(false);
    });
    return () => { cancelled = true; };
  }, [isMobile, mobilePlatform?.value]);

  const uploadAppBinary = async (usecaseId: string, file: File): Promise<boolean> => {
    setUploadStatus('uploading');
    setUploadError('');
    try {
      const result = await api.post('generate-s3-url', {
        fileType: 'app_binary',
        usecaseId,
        platform: mobilePlatform?.value,
        filename: file.name,
      });

      await fetch(result.signedUrl, {
        method: 'PUT',
        body: file,
        headers: { 'Content-Type': 'application/octet-stream' },
      });

      setUploadStatus('success');
      return true;
    } catch (error) {
      console.error('Failed to upload app binary:', error);
      setUploadStatus('error');
      setUploadError((error as Error).message || 'Upload failed');
      return false;
    }
  };

  const uploadBrowserPolicy = async (usecaseId: string, file: File): Promise<boolean> => {
    setPolicyUploadStatus('uploading');
    setPolicyUploadError('');
    try {
      const result = await api.post('generate-s3-url', {
        fileType: 'browser_policy',
        usecaseId,
        filename: file.name,
      });
      await fetch(result.signedUrl, {
        method: 'PUT',
        body: file,
        headers: { 'Content-Type': 'application/json' },
      });
      setPolicyUploadStatus('success');
      return true;
    } catch (error) {
      console.error('Failed to upload browser policy:', error);
      setPolicyUploadStatus('error');
      setPolicyUploadError((error as Error).message || 'Upload failed');
      return false;
    }
  };

  const handleSubmit = async () => {
    setLoading(true);
    try {
      const payload: Record<string, any> = {
        name,
        description,
        active,
        enableCache,
        executing_region: selectedRegion.value,
        model_id: selectedModel?.value,
        tags: tags.split(',').map(tag => tag.trim()).filter(tag => tag),
        test_platform: testPlatform,
      };

      if (isMobile) {
        payload.platform = mobilePlatform?.value;
        if (selectedDevice?.value) {
          payload.device_arn = selectedDevice.value;
        }
        if (isAndroid) {
          payload.app_package = appPackage;
          payload.app_activity = appActivity;
        }
        if (isIOS) {
          payload.bundle_id = bundleId;
        }
      } else {
        payload.starting_url = starting_url;
      }

      const result = await api.post('usecase', payload);

      // Upload app binary after usecase creation if mobile and file selected
      if (isMobile && appBinaryFiles.length > 0 && result?.id) {
        const uploaded = await uploadAppBinary(result.id, appBinaryFiles[0]);
        if (!uploaded) {
          console.warn('Usecase created but app binary upload failed');
        }
      }

      // Upload browser policy after usecase creation if file selected (web tests only)
      if (!isMobile && policyFiles.length > 0 && result?.id) {
        const uploaded = await uploadBrowserPolicy(result.id, policyFiles[0]);
        if (!uploaded) {
          console.warn('Usecase created but browser policy upload failed');
        }
      }

      navigate('/');
    } catch (error) {
      console.error('Failed to create usecase:', error);
    } finally {
      setLoading(false);
    }
  };

  const acceptedExtension = isAndroid ? '.apk' : isIOS ? '.ipa' : '.apk,.ipa';

  return (
    <SpaceBetween direction="vertical" size="l">
      <BreadcrumbGroup
        items={[
          { text: 'Home', href: '/' },
          { text: 'Create Use Case', href: '/create' },
          { text: 'Create Blank', href: '/create/blank' }
        ]}
        onFollow={(event) => {
          event.preventDefault();
          navigate(event.detail.href);
        }}
      />

      <Header
        variant="h1"
        description="Start from scratch and manually configure all use case settings, steps, and validations."
      >
        Create Blank
      </Header>

      <Container>
        <SpaceBetween direction="vertical" size="l">
          {/* 10.1: Platform selector */}
          <FormField label="Test platform">
            <RadioGroup
              value={testPlatform}
              onChange={({ detail }) => setTestPlatform(detail.value)}
              items={[
                { value: 'web', label: 'Web' },
                { value: 'mobile', label: 'Mobile' },
              ]}
            />
          </FormField>

          {/* 10.2: Device Farm region alert */}
          {isMobile && (
            <SpaceBetween direction="vertical" size="s">
              <Alert type="warning">
                Mobile testing is still experimental. Features may change or behave unexpectedly.
              </Alert>
              <Alert type="info">
                Device Farm operations run in the us-west-2 region regardless of the selected execution region.
              </Alert>
            </SpaceBetween>
          )}

          <FormField label="Name">
            <Input
              value={name}
              onChange={({ detail }) => setName(detail.value)}
              placeholder="Enter use case name"
            />
          </FormField>

          <FormField label="Description">
            <Textarea
              value={description}
              onChange={({ detail }) => setDescription(detail.value)}
              placeholder="Enter use case description"
              rows={4}
            />
          </FormField>

          {/* 10.2: Conditional fields based on platform */}
          {!isMobile && (
            <FormField label="Starting URL">
              <Input
                value={starting_url}
                onChange={({ detail }) => setStartingUrl(detail.value)}
                placeholder="https://example.com"
              />
            </FormField>
          )}

          {isMobile && (
            <>
              <FormField label="Mobile platform">
                <Select
                  selectedOption={mobilePlatform}
                  onChange={({ detail }) => setMobilePlatform(detail.selectedOption)}
                  options={platformOptions}
                  placeholder="Select platform"
                />
              </FormField>

              {mobilePlatform && (
                <FormField
                  label="Device"
                  description="Select a specific device or leave empty to auto-select the newest available"
                >
                  <Select
                    selectedOption={selectedDevice}
                    onChange={({ detail }) => setSelectedDevice(detail.selectedOption)}
                    options={deviceOptions}
                    placeholder="Auto-select (newest device)"
                    loadingText="Loading devices..."
                    statusType={devicesLoading ? "loading" : "finished"}
                    filteringType="auto"
                    empty="No devices available"
                  />
                </FormField>
              )}

              {isAndroid && (
                <>
                  <FormField label="App package" description="e.g. com.example.myapp">
                    <Input
                      value={appPackage}
                      onChange={({ detail }) => setAppPackage(detail.value)}
                      placeholder="com.example.myapp"
                    />
                  </FormField>
                  <FormField label="App activity" description="e.g. com.example.myapp.MainActivity">
                    <Input
                      value={appActivity}
                      onChange={({ detail }) => setAppActivity(detail.value)}
                      placeholder="com.example.myapp.MainActivity"
                    />
                  </FormField>
                </>
              )}

              {isIOS && (
                <FormField label="Bundle ID" description="e.g. com.example.myapp">
                  <Input
                    value={bundleId}
                    onChange={({ detail }) => setBundleId(detail.value)}
                    placeholder="com.example.myapp"
                  />
                </FormField>
              )}

              {/* 10.3: App binary upload */}
              <FormField
                label="App binary"
                description={`Upload your ${isAndroid ? '.apk' : isIOS ? '.ipa' : '.apk or .ipa'} file`}
              >
                <SpaceBetween direction="vertical" size="xs">
                  <FileUpload
                    onChange={({ detail }) => {
                      setAppBinaryFiles(detail.value);
                      setUploadStatus('none');
                      setUploadError('');
                    }}
                    value={appBinaryFiles}
                    i18nStrings={{
                      uploadButtonText: () => 'Choose file',
                      dropzoneText: () => 'Drop file to upload',
                      removeFileAriaLabel: (e) => `Remove file ${e + 1}`,
                      limitShowFewer: 'Show fewer files',
                      limitShowMore: 'Show more files',
                      errorIconAriaLabel: 'Error',
                    }}
                    accept={acceptedExtension}
                    constraintText={`Accepted formats: ${acceptedExtension}`}
                    showFileSize
                    showFileLastModified
                  />
                  {uploadStatus === 'uploading' && (
                    <StatusIndicator type="loading">Uploading app binary...</StatusIndicator>
                  )}
                  {uploadStatus === 'success' && (
                    <StatusIndicator type="success">App binary uploaded</StatusIndicator>
                  )}
                  {uploadStatus === 'error' && (
                    <StatusIndicator type="error">{uploadError || 'Upload failed'}</StatusIndicator>
                  )}
                </SpaceBetween>
              </FormField>
            </>
          )}

          <FormField label="Region">
            <Select
              selectedOption={selectedRegion}
              onChange={({ detail }) => setSelectedRegion(detail.selectedOption)}
              options={regionOptions()}
            />
          </FormField>

          <FormField
            label="Model"
            description="Select the Nova Act model to use for this use case"
          >
            <Select
              selectedOption={selectedModel}
              onChange={({ detail }) => setSelectedModel(detail.selectedOption)}
              options={modelOptions()}
              placeholder="Select a model"
              loadingText="Loading models..."
              statusType={modelsLoading ? "loading" : "finished"}
            />
          </FormField>

          <FormField label="Tags">
            <Input
              value={tags}
              onChange={({ detail }) => setTags(detail.value)}
              placeholder="Enter tags separated by commas"
            />
          </FormField>

          {!isMobile && (
          <FormField
            label="Browser policy (optional)"
            description="Upload a Chromium enterprise policy JSON file to control browser behavior (e.g., auto-dismiss permission dialogs)"
          >
            <SpaceBetween direction="vertical" size="xs">
              <FileUpload
                onChange={({ detail }) => {
                  setPolicyFiles(detail.value);
                  setPolicyUploadStatus('none');
                  setPolicyUploadError('');
                }}
                value={policyFiles}
                i18nStrings={{
                  uploadButtonText: () => 'Choose file',
                  dropzoneText: () => 'Drop file to upload',
                  removeFileAriaLabel: (e) => `Remove file ${e + 1}`,
                  limitShowFewer: 'Show fewer files',
                  limitShowMore: 'Show more files',
                  errorIconAriaLabel: 'Error',
                }}
                accept=".json"
                constraintText="Accepted format: .json (Chromium enterprise policy)"
                showFileSize
                showFileLastModified
              />
              {policyUploadStatus === 'uploading' && (
                <StatusIndicator type="loading">Uploading browser policy...</StatusIndicator>
              )}
              {policyUploadStatus === 'success' && (
                <StatusIndicator type="success">Browser policy uploaded</StatusIndicator>
              )}
              {policyUploadStatus === 'error' && (
                <StatusIndicator type="error">{policyUploadError || 'Upload failed'}</StatusIndicator>
              )}
            </SpaceBetween>
          </FormField>
          )}

          <FormField>
            <Checkbox
              checked={active}
              onChange={({ detail }) => setActive(detail.checked)}
            >
              Active
            </Checkbox>
          </FormField>

          <FormField
            label="Step caching"
            description="Cache navigation steps to reduce execution time by 40-60%"
          >
            <Toggle
              checked={enableCache}
              onChange={({ detail }) => setEnableCache(detail.checked)}
            >
              Enable step caching
            </Toggle>
          </FormField>

          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="primary" onClick={handleSubmit} loading={loading} disabled={loading}>
              Create
            </Button>
            <Button onClick={() => navigate('/create')} disabled={loading}>
              Cancel
            </Button>
          </SpaceBetween>
        </SpaceBetween>
      </Container>
    </SpaceBetween>
  );
}
