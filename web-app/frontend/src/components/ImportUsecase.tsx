import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import FormField from "@cloudscape-design/components/form-field";
import FileUpload from "@cloudscape-design/components/file-upload";
import Alert from "@cloudscape-design/components/alert";
import ExpandableSection from "@cloudscape-design/components/expandable-section";
import Table from "@cloudscape-design/components/table";
import BreadcrumbGroup from "@cloudscape-design/components/breadcrumb-group";
import Input from "@cloudscape-design/components/input";
import Select, { SelectProps } from "@cloudscape-design/components/select";
import { exportImportApi, api } from '../utils/api';
import { regionOptions, findRegionOptions } from '../utils/browser_regions';

export default function ImportUsecase() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File[]>([]);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<any>(null);
  const [error, setError] = useState<string>('');
  const [filePreview, setFilePreview] = useState<any>(null);
  const [previewError, setPreviewError] = useState<string>('');
  const [showSecretsForm, setShowSecretsForm] = useState(false);
  const [secretValues, setSecretValues] = useState<Record<string, string>>({});
  const [savingSecrets, setSavingSecrets] = useState(false);
  const [selectedRegion, setSelectedRegion] = useState<SelectProps.Option | null>(findRegionOptions() as SelectProps.Option);

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
      
      if (selectedRegion?.value) {
        importData.regionOverride = selectedRegion.value;
      }

      const result = await exportImportApi.importUsecase(importData);
      setImportResult(result);
      
      if (result.success) {
        // Check if there are secrets that need to be configured
        if (result.missingSecrets && result.missingSecrets.length > 0) {
          // Initialize secret values
          const initialSecretValues: Record<string, string> = {};
          result.missingSecrets.forEach((secretKey: string) => {
            initialSecretValues[secretKey] = '';
          });
          setSecretValues(initialSecretValues);
          setShowSecretsForm(true);
        } else {
          // No secrets needed, redirect after a short delay
          setTimeout(() => {
            navigate('/');
          }, 2000);
        }
      }
    } catch (error: any) {
      console.error('Import failed:', error);
      setError(error.message || 'Failed to import usecase');
    } finally {
      setImporting(false);
    }
  };

  const handleSaveSecrets = async () => {
    if (!importResult?.usecaseId) return;

    setSavingSecrets(true);
    setError('');
    
    try {
      // Build secrets array with only non-empty values
      const secretsToSave = Object.entries(secretValues)
        .filter(([_, value]) => value.trim())
        .map(([key, value]) => ({
          key,
          value: value.trim()
        }));

      if (secretsToSave.length > 0) {
        await api.post(`usecase/${importResult.usecaseId}/secrets`, { 
          secrets: secretsToSave 
        });
      }
      
      // Navigate to the usecase detail page
      navigate(`/usecase/${importResult.usecaseId}`);
    } catch (error: any) {
      console.error('Failed to save secrets:', error);
      setError(error.message || 'Failed to save secrets');
      setSavingSecrets(false);
    }
  };

  const handleSkipSecrets = () => {
    if (importResult?.usecaseId) {
      navigate(`/usecase/${importResult.usecaseId}`);
    } else {
      navigate('/');
    }
  };

  return (
    <SpaceBetween direction="vertical" size="l">
      <BreadcrumbGroup
        items={[
          { text: 'Home', href: '/' },
          { text: 'Create Use Case', href: '/create' },
          { text: 'Import Use Case', href: '/create/import' }
        ]}
        onFollow={(event) => {
          event.preventDefault();
          navigate(event.detail.href);
        }}
      />

      <Header
        variant="h1"
        description="Import a previously exported use case from a JSON file."
      >
        Import Use Case
      </Header>

      <Container>
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

          <FormField
            label="Execution region"
            description="AWS region where the browser will run during test execution"
          >
            <Select
              selectedOption={selectedRegion}
              onChange={({ detail }) => setSelectedRegion(detail.selectedOption)}
              options={regionOptions()}
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
                  {filePreview.usecase?.region && (
                    <div style={{ marginTop: '4px', color: '#5f6b7a' }}>
                      <strong>Region:</strong> {filePreview.usecase.region}
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
                            cell: (item: any) => item.key
                          },
                          {
                            id: "description",
                            header: "Description",
                            cell: (item: any) => item.description || item.placeholder || "-"
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

          {importResult && !showSecretsForm && (
            <Alert 
              type={importResult.success ? "success" : "error"} 
              statusIconAriaLabel={importResult.success ? "Success" : "Error"}
            >
              <SpaceBetween direction="vertical" size="s">
                <div>{importResult.message}</div>
                
                {importResult.success && !importResult.missingSecrets?.length && (
                  <div style={{ marginTop: '8px', color: '#5f6b7a' }}>
                    Redirecting to home page...
                  </div>
                )}
              </SpaceBetween>
            </Alert>
          )}

          {!showSecretsForm && (
            <SpaceBetween direction="horizontal" size="xs">
              <Button 
                variant="primary" 
                onClick={handleImport}
                loading={importing}
                disabled={!file[0] || importing || importResult?.success}
              >
                {importing ? 'Importing...' : 'Import Use Case'}
              </Button>
              <Button 
                onClick={() => navigate('/create')} 
                disabled={importing}
              >
                Cancel
              </Button>
            </SpaceBetween>
          )}
        </SpaceBetween>
      </Container>

      {showSecretsForm && importResult?.success && (
        <Container
          header={
            <Header
              variant="h2"
              description="Configure secret values for the imported use case"
            >
              Configure Secrets
            </Header>
          }
        >
          <SpaceBetween direction="vertical" size="l">
            <Alert type="info" statusIconAriaLabel="Info">
              The imported use case requires the following secrets. You can configure them now or skip and add them later.
            </Alert>

            {error && (
              <Alert type="error" statusIconAriaLabel="Error">
                {error}
              </Alert>
            )}

            {importResult.missingSecrets.map((secretKey: string) => {
              const secretInfo = filePreview?.secrets?.find((s: any) => s.key === secretKey);
              return (
                <FormField
                  key={secretKey}
                  label={secretKey}
                  description={secretInfo?.description || secretInfo?.placeholder || 'Enter the secret value'}
                >
                  <Input
                    value={secretValues[secretKey] || ''}
                    onChange={({ detail }) => 
                      setSecretValues(prev => ({ ...prev, [secretKey]: detail.value }))
                    }
                    type="password"
                    placeholder="Enter secret value"
                  />
                </FormField>
              );
            })}

            <SpaceBetween direction="horizontal" size="xs">
              <Button 
                variant="primary" 
                onClick={handleSaveSecrets}
                loading={savingSecrets}
                disabled={savingSecrets}
              >
                Save Secrets
              </Button>
              <Button 
                onClick={handleSkipSecrets}
                disabled={savingSecrets}
              >
                Skip for Now
              </Button>
            </SpaceBetween>
          </SpaceBetween>
        </Container>
      )}
    </SpaceBetween>
  );
}
