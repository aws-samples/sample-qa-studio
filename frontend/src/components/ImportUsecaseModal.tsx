import React, { useState, useEffect } from 'react';
import Modal from "@cloudscape-design/components/modal";
import Box from "@cloudscape-design/components/box";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import FormField from "@cloudscape-design/components/form-field";
import FileUpload from "@cloudscape-design/components/file-upload";
import Alert from "@cloudscape-design/components/alert";
import StatusIndicator from "@cloudscape-design/components/status-indicator";
import ExpandableSection from "@cloudscape-design/components/expandable-section";
import Table from "@cloudscape-design/components/table";
import Header from "@cloudscape-design/components/header";
import { exportImportApi } from '../utils/api';

interface ImportUsecaseModalProps {
  visible: boolean;
  onDismiss: () => void;
  onImportSuccess: () => void;
}

export default function ImportUsecaseModal({ visible, onDismiss, onImportSuccess }: ImportUsecaseModalProps) {
  const [file, setFile] = useState<File[]>([]);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<any>(null);
  const [error, setError] = useState<string>('');
  const [filePreview, setFilePreview] = useState<any>(null);
  const [previewError, setPreviewError] = useState<string>('');

  // Preview file content when file is selected
  useEffect(() => {
    const previewFile = async () => {
      if (!file[0]) {
        setFilePreview(null);
        setPreviewError('');
        return;
      }

      try {
        const fileContent = await file[0].text();
        const importData = JSON.parse(fileContent);
        
        // Validate basic structure
        if (!importData.usecase || !importData.exportVersion) {
          setPreviewError('Invalid export file format');
          setFilePreview(null);
          return;
        }

        setFilePreview(importData);
        setPreviewError('');
      } catch (error) {
        setPreviewError('Failed to read or parse file');
        setFilePreview(null);
      }
    };

    previewFile();
  }, [file]);

  const handleImport = async () => {
    if (!file[0]) return;

    setImporting(true);
    setError('');
    setImportResult(null);

    try {
      const fileContent = await file[0].text();
      const importData = JSON.parse(fileContent);
      
      const result = await exportImportApi.importUsecase(importData);
      setImportResult(result);
      
      if (result.success) {
        onImportSuccess();
      }
    } catch (error: any) {
      console.error('Import failed:', error);
      setError(error.message || 'Failed to import usecase');
    } finally {
      setImporting(false);
    }
  };

  const handleClose = () => {
    setFile([]);
    setImportResult(null);
    setError('');
    setFilePreview(null);
    setPreviewError('');
    onDismiss();
  };

  return (
    <Modal
      onDismiss={handleClose}
      visible={visible}
      closeAriaLabel="Close modal"
      size="medium"
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={handleClose}>
              Cancel
            </Button>
            <Button 
              variant="primary" 
              onClick={handleImport}
              loading={importing}
              disabled={!file[0] || importing}
            >
              {importing ? 'Importing...' : 'Import Usecase'}
            </Button>
          </SpaceBetween>
        </Box>
      }
      header="Import Usecase"
    >
      <SpaceBetween direction="vertical" size="l">
        <FormField
          label="Select export file"
          description="Choose a JSON file exported from another usecase"
        >
          <FileUpload
            onChange={({ detail }) => setFile(detail.value)}
            value={file}
            i18nStrings={{
              uploadButtonText: e => e ? "Choose files" : "Choose file",
              dropzoneText: e => e ? "Drop files to upload" : "Drop file to upload",
              removeFileAriaLabel: e => `Remove file ${e + 1}`,
              limitShowFewer: "Show fewer files",
              limitShowMore: "Show more files",
              errorIconAriaLabel: "Error"
            }}
            showFileLastModified
            showFileSize
            showFileThumbnail
            tokenLimit={3}
            accept=".json"
          />
        </FormField>

        {error && (
          <Alert type="error" statusIconAriaLabel="Error">
            {error}
          </Alert>
        )}

        {previewError && (
          <Alert type="error" statusIconAriaLabel="Error">
            {previewError}
          </Alert>
        )}

        {filePreview && (
          <ExpandableSection headerText="Import Preview" defaultExpanded={true}>
            <SpaceBetween direction="vertical" size="m">
              <div>
                <strong>Usecase:</strong> {filePreview.usecase?.name || 'Unknown'}
                {filePreview.usecase?.description && (
                  <div style={{ marginTop: '4px', color: '#5f6b7a' }}>
                    {filePreview.usecase.description}
                  </div>
                )}
              </div>

              <div>
                <strong>Export Version:</strong> {filePreview.exportVersion}
                <br />
                <strong>Exported At:</strong> {new Date(filePreview.exportedAt).toLocaleString()}
              </div>

              <div>
                <strong>Content:</strong>
                <ul style={{ margin: '4px 0', paddingLeft: '20px' }}>
                  <li>{filePreview.steps?.length || 0} steps</li>
                  <li>{filePreview.variables?.length || 0} variables</li>
                  <li>{filePreview.secrets?.length || 0} secrets</li>
                  {filePreview.hooks && <li>Hooks configuration</li>}
                </ul>
              </div>

              {filePreview.secrets && filePreview.secrets.length > 0 && (
                <Alert type="warning" statusIconAriaLabel="Warning">
                  <SpaceBetween direction="vertical" size="s">
                    <div>
                      <strong>Secrets Configuration Required</strong>
                    </div>
                    <div>
                      The following secrets will be created but need to be configured with actual values after import:
                    </div>
                    <Table
                      columnDefinitions={[
                        {
                          id: "key",
                          header: "Secret Key",
                          cell: item => item.key
                        },
                        {
                          id: "description",
                          header: "Description",
                          cell: item => item.description || item.placeholder || "-"
                        }
                      ]}
                      items={filePreview.secrets}
                      empty="No secrets found"
                      variant="embedded"
                    />
                  </SpaceBetween>
                </Alert>
              )}
            </SpaceBetween>
          </ExpandableSection>
        )}

        {importResult && (
          <Alert 
            type={importResult.success ? "success" : "error"} 
            statusIconAriaLabel={importResult.success ? "Success" : "Error"}
          >
            <SpaceBetween direction="vertical" size="s">
              <div>{importResult.message}</div>
              
              {importResult.success && importResult.missingSecrets && importResult.missingSecrets.length > 0 && (
                <div>
                  <strong>Note:</strong> The following secrets need to be configured in the imported usecase:
                  <ul>
                    {importResult.missingSecrets.map((secret: string) => (
                      <li key={secret}>{secret}</li>
                    ))}
                  </ul>
                </div>
              )}
            </SpaceBetween>
          </Alert>
        )}
      </SpaceBetween>
    </Modal>
  );
}