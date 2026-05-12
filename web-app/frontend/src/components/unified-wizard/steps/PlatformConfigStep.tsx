import React, { useEffect, useState } from 'react';
import Container from '@cloudscape-design/components/container';
import Alert from '@cloudscape-design/components/alert';
import SpaceBetween from '@cloudscape-design/components/space-between';
import FormField from '@cloudscape-design/components/form-field';
import Input from '@cloudscape-design/components/input';
import Toggle from '@cloudscape-design/components/toggle';
import Select, { SelectProps } from '@cloudscape-design/components/select';
import FileUpload from '@cloudscape-design/components/file-upload';
import type { StepProps } from '../types';
import { devicesApi } from '../../../utils/api';

export default function PlatformConfigStep({ state, dispatch, validationErrors }: StepProps) {
  const [deviceOptions, setDeviceOptions] = useState<SelectProps.Options>([]);
  const [devicesLoading, setDevicesLoading] = useState(false);

  const isWeb = state.testPlatform === 'web';
  const isMobile = state.testPlatform === 'mobile';
  const isAndroid = state.mobilePlatform === 'ANDROID';
  const isIOS = state.mobilePlatform === 'IOS';

  // Fetch Device Farm devices when mobile platform changes
  useEffect(() => {
    if (!isMobile || !state.mobilePlatform) {
      setDeviceOptions([]);
      return;
    }

    let cancelled = false;
    setDevicesLoading(true);

    devicesApi.list(state.mobilePlatform).then((data) => {
      if (cancelled) return;
      const options = data.devices.map((d) => ({
        label: `${d.name} (${d.os})`,
        value: d.arn,
        description: `${d.manufacturer} · ${d.formFactor}`,
      }));
      setDeviceOptions(options);
    }).catch((err) => {
      if (!cancelled) console.error('Failed to load devices:', err);
    }).finally(() => {
      if (!cancelled) setDevicesLoading(false);
    });

    return () => { cancelled = true; };
  }, [isMobile, state.mobilePlatform]);

  const selectedDeviceOption: SelectProps.Option | null = state.blankConfig.deviceArn
    ? deviceOptions.find((o) => (o as SelectProps.Option).value === state.blankConfig.deviceArn) as SelectProps.Option ?? { label: state.blankConfig.deviceArn, value: state.blankConfig.deviceArn }
    : null;

  return (
    <Container>
      <SpaceBetween direction="vertical" size="l">
        {/* --- Mobile: Platform Selection & Device Farm Alert --- */}
        {isMobile && (
          <>
            <Alert type="info">
              Device Farm operations run in the <strong>us-west-2</strong> region regardless of the selected execution region.
            </Alert>
            <FormField
              label="Mobile platform"
              errorText={validationErrors.mobilePlatform}
            >
              <Select
                selectedOption={
                  state.mobilePlatform
                    ? { label: state.mobilePlatform === 'ANDROID' ? 'Android' : 'iOS', value: state.mobilePlatform }
                    : null
                }
                onChange={({ detail }) =>
                  dispatch({ type: 'SET_MOBILE_PLATFORM', payload: detail.selectedOption.value ?? null })
                }
                options={[
                  { label: 'Android', value: 'ANDROID' },
                  { label: 'iOS', value: 'IOS' },
                ]}
                placeholder="Select platform"
              />
            </FormField>
          </>
        )}

        {/* --- Web Platform Fields --- */}
        {isWeb && (
          <>
            <FormField
              label="Browser policy (optional)"
              description="Upload a Chromium enterprise policy JSON file to control browser behavior"
            >
              <FileUpload
                onChange={({ detail }) =>
                  dispatch({
                    type: 'UPDATE_BLANK_CONFIG',
                    payload: { browserPolicyFile: detail.value[0] ?? null },
                  })
                }
                value={state.blankConfig.browserPolicyFile ? [state.blankConfig.browserPolicyFile] : []}
                i18nStrings={{
                  uploadButtonText: () => 'Choose file',
                  dropzoneText: () => 'Drop file to upload',
                  removeFileAriaLabel: (e) => `Remove file ${e + 1}`,
                  limitShowFewer: 'Show fewer files',
                  limitShowMore: 'Show more files',
                  errorIconAriaLabel: 'Error',
                }}
                accept=".json"
                constraintText="Accepted format: .json"
                showFileSize
                showFileLastModified
              />
            </FormField>
          </>
        )}

        {/* --- Mobile / Android Fields --- */}
        {isMobile && isAndroid && (
          <>
            <FormField
              label="App package"
              description="e.g. com.example.myapp"
              errorText={validationErrors.appPackage}
            >
              <Input
                value={state.blankConfig.appPackage}
                onChange={({ detail }) =>
                  dispatch({ type: 'UPDATE_BLANK_CONFIG', payload: { appPackage: detail.value } })
                }
                placeholder="com.example.myapp"
              />
            </FormField>

            <FormField
              label="App activity"
              description="e.g. com.example.myapp.MainActivity"
              errorText={validationErrors.appActivity}
            >
              <Input
                value={state.blankConfig.appActivity}
                onChange={({ detail }) =>
                  dispatch({ type: 'UPDATE_BLANK_CONFIG', payload: { appActivity: detail.value } })
                }
                placeholder="com.example.myapp.MainActivity"
              />
            </FormField>
          </>
        )}

        {/* --- Mobile / iOS Fields --- */}
        {isMobile && isIOS && (
          <FormField
            label="Bundle ID"
            description="e.g. com.example.myapp"
            errorText={validationErrors.bundleId}
          >
            <Input
              value={state.blankConfig.bundleId}
              onChange={({ detail }) =>
                dispatch({ type: 'UPDATE_BLANK_CONFIG', payload: { bundleId: detail.value } })
              }
              placeholder="com.example.myapp"
            />
          </FormField>
        )}

        {/* --- Mobile: Device Selection (Android & iOS) --- */}
        {isMobile && state.mobilePlatform && (
          <FormField
            label="Device"
            description="Select a device from AWS Device Farm"
            errorText={validationErrors.deviceArn}
          >
            <Select
              selectedOption={selectedDeviceOption}
              onChange={({ detail }) =>
                dispatch({
                  type: 'UPDATE_BLANK_CONFIG',
                  payload: { deviceArn: detail.selectedOption.value ?? null },
                })
              }
              options={deviceOptions}
              placeholder="Auto-select (newest device)"
              loadingText="Loading devices..."
              statusType={devicesLoading ? 'loading' : 'finished'}
              filteringType="auto"
              empty="No devices available"
            />
          </FormField>
        )}

        {/* --- Mobile: App Binary Upload --- */}
        {isMobile && isAndroid && (
          <FormField
            label="App binary"
            description="Upload your .apk file"
          >
            <FileUpload
              onChange={({ detail }) =>
                dispatch({
                  type: 'UPDATE_BLANK_CONFIG',
                  payload: { appBinaryFile: detail.value[0] ?? null },
                })
              }
              value={state.blankConfig.appBinaryFile ? [state.blankConfig.appBinaryFile] : []}
              i18nStrings={{
                uploadButtonText: () => 'Choose file',
                dropzoneText: () => 'Drop file to upload',
                removeFileAriaLabel: (e) => `Remove file ${e + 1}`,
                limitShowFewer: 'Show fewer files',
                limitShowMore: 'Show more files',
                errorIconAriaLabel: 'Error',
              }}
              accept=".apk"
              constraintText="Accepted format: .apk"
              showFileSize
              showFileLastModified
            />
          </FormField>
        )}

        {isMobile && isIOS && (
          <FormField
            label="App binary"
            description="Upload your .ipa file"
          >
            <FileUpload
              onChange={({ detail }) =>
                dispatch({
                  type: 'UPDATE_BLANK_CONFIG',
                  payload: { appBinaryFile: detail.value[0] ?? null },
                })
              }
              value={state.blankConfig.appBinaryFile ? [state.blankConfig.appBinaryFile] : []}
              i18nStrings={{
                uploadButtonText: () => 'Choose file',
                dropzoneText: () => 'Drop file to upload',
                removeFileAriaLabel: (e) => `Remove file ${e + 1}`,
                limitShowFewer: 'Show fewer files',
                limitShowMore: 'Show more files',
                errorIconAriaLabel: 'Error',
              }}
              accept=".ipa"
              constraintText="Accepted format: .ipa"
              showFileSize
              showFileLastModified
            />
          </FormField>
        )}

        {/* --- Step Caching Toggle --- */}
        {isWeb && (
          <FormField
            label="Step caching (experimental)"
            description="Cache navigation steps to reduce execution time by 40-60%. This feature is experimental."
          >
            <Toggle
              checked={state.blankConfig.enableCache}
              onChange={({ detail }) =>
                dispatch({ type: 'UPDATE_BLANK_CONFIG', payload: { enableCache: detail.checked } })
              }
            >
              Enable step caching
            </Toggle>
          </FormField>
        )}

      </SpaceBetween>
    </Container>
  );
}
