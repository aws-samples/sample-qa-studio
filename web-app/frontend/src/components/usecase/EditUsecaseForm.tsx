import React, { useState } from 'react';
import SpaceBetween from "@cloudscape-design/components/space-between";
import FormField from "@cloudscape-design/components/form-field";
import Input from "@cloudscape-design/components/input";
import Textarea from "@cloudscape-design/components/textarea";
import Checkbox from "@cloudscape-design/components/checkbox";
import Toggle from "@cloudscape-design/components/toggle";
import Button from "@cloudscape-design/components/button";
import Select, { SelectProps } from "@cloudscape-design/components/select";
import Alert from "@cloudscape-design/components/alert";
import FileUpload from "@cloudscape-design/components/file-upload";
import StatusIndicator from "@cloudscape-design/components/status-indicator";
import Badge from "@cloudscape-design/components/badge";
import { regionOptions, findRegionOptions } from './../../utils/browser_regions';
import { useModels } from '../../hooks/useModels';
import { api } from '../../utils/api';
import { devicesApi } from '../../utils/api';

const platformOptions: SelectProps.Options = [
  { label: 'Android', value: 'ANDROID' },
  { label: 'iOS', value: 'IOS' },
];

interface EditUsecaseFormProps {
  usecase: any;
  onSave: (updatedUsecase: any) => void;
  onCancel: () => void;
}

export default function EditUsecaseForm({ usecase, onSave, onCancel }: EditUsecaseFormProps) {
  const [name, setName] = useState(usecase.name || '');
  const [description, setDescription] = useState(usecase.description || '');
  const [starting_url, setStartingUrl] = useState(usecase.starting_url || '');
  const [active, setActive] = useState(usecase.active || false);
  const [enableCache, setEnableCache] = useState(usecase.enableCache || false);
  const [tags, setTags] = useState(usecase.tags?.join(', ') || '');
  const [selectedRegion, setSelectedRegion] = useState(findRegionOptions(usecase.executing_region) as SelectProps.Option);
  const { modelOptions, findModelOption, loading: modelsLoading } = useModels();
  const [selectedModel, setSelectedModel] = useState<SelectProps.Option | null>(null);

  // Mobile-specific state
  const isMobile = (usecase.test_platform || 'web') === 'mobile';
  const [mobilePlatform, setMobilePlatform] = useState<SelectProps.Option | null>(
    usecase.platform ? platformOptions.find(o => (o as SelectProps.Option).value === usecase.platform) as SelectProps.Option || null : null
  );
  const [appPackage, setAppPackage] = useState(usecase.app_package || '');
  const [appActivity, setAppActivity] = useState(usecase.app_activity || '');
  const [bundleId, setBundleId] = useState(usecase.bundle_id || '');
  const [appBinaryFiles, setAppBinaryFiles] = useState<File[]>([]);
  const [uploadStatus, setUploadStatus] = useState<'none' | 'uploading' | 'success' | 'error'>('none');
  const [uploadError, setUploadError] = useState('');
  const [deviceOptions, setDeviceOptions] = useState<SelectProps.Options>([]);
  const [selectedDevice, setSelectedDevice] = useState<SelectProps.Option | null>(
    usecase.device_arn ? { label: usecase.device_arn, value: usecase.device_arn } : null
  );
  const [devicesLoading, setDevicesLoading] = useState(false);

  const isAndroid = mobilePlatform?.value === 'ANDROID';
  const isIOS = mobilePlatform?.value === 'IOS';

  // Browser policy state
  const [policyFiles, setPolicyFiles] = useState<File[]>([]);
  const [policyUploadStatus, setPolicyUploadStatus] = useState<'none' | 'uploading' | 'success' | 'error'>('none');
  const [policyUploadError, setPolicyUploadError] = useState('');

  // Fetch Device Farm devices when mobile platform is set
  React.useEffect(() => {
    if (!isMobile || !mobilePlatform?.value) {
      setDeviceOptions([]);
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
      // Match existing device_arn to the loaded options
      if (usecase.device_arn) {
        const match = options.find(o => o.value === usecase.device_arn);
        if (match) setSelectedDevice(match);
      }
    }).catch(err => {
      if (!cancelled) console.error('Failed to load devices:', err);
    }).finally(() => {
      if (!cancelled) setDevicesLoading(false);
    });
    return () => { cancelled = true; };
  }, [isMobile, mobilePlatform?.value, usecase.device_arn]);

  // Set model from usecase or default
  React.useEffect(() => {
    if (!modelsLoading && !selectedModel) {
      setSelectedModel(findModelOption(usecase.model_id));
    }
  }, [modelsLoading, selectedModel, usecase.model_id, findModelOption]);

  const uploadAppBinary = async (file: File): Promise<boolean> => {
    setUploadStatus('uploading');
    setUploadError('');
    try {
      const result = await api.post('generate-s3-url', {
        fileType: 'app_binary',
        usecaseId: usecase.id,
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

  const uploadBrowserPolicy = async (file: File): Promise<boolean> => {
    setPolicyUploadStatus('uploading');
    setPolicyUploadError('');
    try {
      const result = await api.post('generate-s3-url', {
        fileType: 'browser_policy',
        usecaseId: usecase.id,
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

  const handleSave = async () => {
    // Upload app binary first if a new file was selected
    if (isMobile && appBinaryFiles.length > 0) {
      const uploaded = await uploadAppBinary(appBinaryFiles[0]);
      if (!uploaded) {
        return; // Don't save if upload failed
      }
    }

    // Upload browser policy if a new file was selected
    if (policyFiles.length > 0) {
      const uploaded = await uploadBrowserPolicy(policyFiles[0]);
      if (!uploaded) {
        return; // Don't save if upload failed
      }
    }

    const updatedUsecase: Record<string, any> = {
      name,
      description,
      starting_url,
      active,
      enableCache,
      executing_region: selectedRegion.value,
      model_id: selectedModel?.value,
      tags: tags.split(',').map((tag: string) => tag.trim()).filter((tag: string) => tag.length > 0),
      test_platform: usecase.test_platform || 'web',
    };

    if (isMobile) {
      updatedUsecase.platform = mobilePlatform?.value;
      if (selectedDevice?.value) {
        updatedUsecase.device_arn = selectedDevice.value;
      }
      if (isAndroid) {
        updatedUsecase.app_package = appPackage;
        updatedUsecase.app_activity = appActivity;
      }
      if (isIOS) {
        updatedUsecase.bundle_id = bundleId;
      }
    }

    onSave(updatedUsecase);
  };

  const acceptedExtension = isAndroid ? '.apk' : isIOS ? '.ipa' : '.apk,.ipa';

  return (
    <SpaceBetween direction="vertical" size="m">
      {isMobile && (
        <Alert type="info">
          This is a <Badge color="blue">Mobile</Badge> use case. Device Farm operations run in us-west-2.
        </Alert>
      )}

      <FormField label="Name">
        <Input
          value={name}
          onChange={({ detail }) => setName(detail.value)}
          placeholder="Enter usecase name"
        />
      </FormField>

      <FormField label="Description">
        <Textarea
          value={description}
          onChange={({ detail }) => setDescription(detail.value)}
          placeholder="Enter usecase description"
          rows={3}
        />
      </FormField>

      {!isMobile && (
        <FormField label="Starting URL">
          <Input
            value={starting_url}
            onChange={({ detail }) => setStartingUrl(detail.value)}
            placeholder="https://example.com"
            type="url"
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

          <FormField
            label="App binary"
            description={
              usecase.app_binary_s3_path
                ? `Current: ${usecase.app_binary_s3_path.split('/').pop()} — upload a new file to replace`
                : `Upload your ${isAndroid ? '.apk' : isIOS ? '.ipa' : '.apk or .ipa'} file`
            }
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
                  uploadButtonText: () => usecase.app_binary_s3_path ? 'Replace file' : 'Choose file',
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

      <FormField
        label="Browser policy"
        description={
          usecase.browser_policy_s3_path
            ? `Current: ${usecase.browser_policy_s3_path.split('/').pop()} — upload a new file to replace`
            : 'Optional: Upload a Chromium enterprise policy JSON file to control browser behavior (e.g., auto-dismiss permission dialogs)'
        }
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
              uploadButtonText: () => usecase.browser_policy_s3_path ? 'Replace policy' : 'Choose file',
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

      <FormField label="Region">
        <Select
          selectedOption={selectedRegion}
          onChange={({ detail }) =>
            setSelectedRegion(detail.selectedOption)
          }
          options={regionOptions()}
        />
      </FormField>

      <FormField 
        label="Model"
        description="Select the Nova Act model to use for this use case"
      >
        <Select
          selectedOption={selectedModel}
          onChange={({ detail }) =>
            setSelectedModel(detail.selectedOption)
          }
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
          placeholder="tag1, tag2, tag3"
        />
      </FormField>

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
        <Button variant="primary" onClick={handleSave}>
          Save Changes
        </Button>
        <Button onClick={onCancel}>
          Cancel
        </Button>
      </SpaceBetween>
    </SpaceBetween>
  );
}