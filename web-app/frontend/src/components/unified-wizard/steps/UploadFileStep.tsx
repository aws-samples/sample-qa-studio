import { useEffect } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import FormField from "@cloudscape-design/components/form-field";
import FileUpload from "@cloudscape-design/components/file-upload";
import Alert from "@cloudscape-design/components/alert";
import Box from "@cloudscape-design/components/box";
import ColumnLayout from "@cloudscape-design/components/column-layout";
import type { StepProps } from '../types';
import { parseImportFile } from '../validation';

export default function UploadFileStep({ state, dispatch, validationErrors }: StepProps) {
  const { importConfig } = state;

  // Parse file content when file changes
  useEffect(() => {
    const processFile = async () => {
      if (!importConfig.file) {
        dispatch({
          type: 'UPDATE_IMPORT_CONFIG',
          payload: {
            parsedData: null,
            parseError: null,
            missingSecrets: [],
          },
        });
        return;
      }

      try {
        const fileContent = await importConfig.file.text();
        const result = parseImportFile(fileContent);

        if (result.success) {
          // Extract secret keys for the warning
          const rawParsed = JSON.parse(fileContent);
          const secrets: any[] = rawParsed.secrets || [];
          const secretKeys = secrets.map((s: any) => s.key || s.name || 'unknown');

          dispatch({
            type: 'UPDATE_IMPORT_CONFIG',
            payload: {
              parsedData: result.data,
              parseError: null,
              missingSecrets: secretKeys.length > 0 ? secretKeys : [],
            },
          });
        } else {
          dispatch({
            type: 'UPDATE_IMPORT_CONFIG',
            payload: {
              parsedData: null,
              parseError: result.error,
              missingSecrets: [],
            },
          });
        }
      } catch {
        dispatch({
          type: 'UPDATE_IMPORT_CONFIG',
          payload: {
            parsedData: null,
            parseError: 'Failed to read file',
            missingSecrets: [],
          },
        });
      }
    };

    processFile();
  }, [importConfig.file]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleFileChange = (files: File[]) => {
    dispatch({
      type: 'UPDATE_IMPORT_CONFIG',
      payload: {
        file: files[0] || null,
        parsedData: null,
        parseError: null,
        missingSecrets: [],
      },
    });
  };

  return (
    <SpaceBetween direction="vertical" size="l">
      <Container>
        <SpaceBetween direction="vertical" size="l">
          <FormField
            label="Select export file"
            description="Choose a JSON file exported from another use case"
            errorText={validationErrors.file || validationErrors.parseError}
          >
            <FileUpload
              onChange={({ detail }) => handleFileChange(detail.value)}
              value={importConfig.file ? [importConfig.file] : []}
              i18nStrings={{
                uploadButtonText: (e) => (e ? 'Choose files' : 'Choose file'),
                dropzoneText: (e) => (e ? 'Drop files to upload' : 'Drop file to upload'),
                removeFileAriaLabel: (e) => `Remove file ${e + 1}`,
                limitShowFewer: 'Show fewer files',
                limitShowMore: 'Show more files',
                errorIconAriaLabel: 'Error',
              }}
              showFileLastModified
              showFileSize
              showFileThumbnail
              tokenLimit={3}
              accept=".json"
            />
          </FormField>

          {importConfig.parseError && (
            <Alert type="error">
              {importConfig.parseError}
            </Alert>
          )}
        </SpaceBetween>
      </Container>

      {importConfig.parsedData && (
        <Container header={<Header variant="h2">Import preview</Header>}>
          <SpaceBetween direction="vertical" size="m">
            <ColumnLayout columns={2} variant="text-grid">
              <div>
                <Box variant="awsui-key-label">Name</Box>
                <div>{importConfig.parsedData.name || 'Unknown'}</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Export Version</Box>
                <div>{importConfig.parsedData.exportVersion}</div>
              </div>
              {importConfig.parsedData.region && (
                <div>
                  <Box variant="awsui-key-label">Region</Box>
                  <div>{importConfig.parsedData.region}</div>
                </div>
              )}
              {importConfig.parsedData.exportDate && (
                <div>
                  <Box variant="awsui-key-label">Export Date</Box>
                  <div>{new Date(importConfig.parsedData.exportDate).toLocaleString()}</div>
                </div>
              )}
              <div>
                <Box variant="awsui-key-label">Steps</Box>
                <div>{importConfig.parsedData.stepCount} step(s)</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Variables</Box>
                <div>{importConfig.parsedData.variableCount} variable(s)</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Secrets</Box>
                <div>{importConfig.parsedData.secretCount} secret(s)</div>
              </div>
            </ColumnLayout>

            {importConfig.parsedData.usecase?.description && (
              <div>
                <Box variant="awsui-key-label">Description</Box>
                <div>{importConfig.parsedData.usecase.description}</div>
              </div>
            )}
          </SpaceBetween>
        </Container>
      )}

      {importConfig.missingSecrets.length > 0 && (
        <Alert type="warning">
          <SpaceBetween direction="vertical" size="xs">
            <Box fontWeight="bold">Secrets configuration required</Box>
            <div>
              The following secrets will need to be configured with actual values after import:
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
  );
}
