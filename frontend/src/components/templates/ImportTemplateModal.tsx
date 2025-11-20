import { useState, useEffect } from 'react';
import Modal from "@cloudscape-design/components/modal";
import Box from "@cloudscape-design/components/box";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import FormField from "@cloudscape-design/components/form-field";
import Select from "@cloudscape-design/components/select";
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import Badge from "@cloudscape-design/components/badge";
import Spinner from "@cloudscape-design/components/spinner";
import Alert from "@cloudscape-design/components/alert";
import { api } from '../../utils/api';

interface Template {
  id: string;
  name: string;
  description: string;
  category: string;
  tags?: string[];
  version: number;
}

interface TemplateStep {
  id: string;
  sort: number;
  instruction: string;
  step_type: string;
}

interface ImportTemplateModalProps {
  visible: boolean;
  usecaseId: string;
  onDismiss: () => void;
  onSuccess: () => void;
}

export default function ImportTemplateModal({ visible, usecaseId, onDismiss, onSuccess }: ImportTemplateModalProps) {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<any>(null);
  const [templateSteps, setTemplateSteps] = useState<TemplateStep[]>([]);
  const [templateVariables, setTemplateVariables] = useState<Array<{key: string, value: string}>>([]);
  const [requiredSecrets, setRequiredSecrets] = useState<string[]>([]);
  const [insertPosition, setInsertPosition] = useState<any>({ label: 'At the end', value: '-1' });
  const [loading, setLoading] = useState(false);
  const [loadingSteps, setLoadingSteps] = useState(false);
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    if (visible) {
      fetchTemplates();
    }
  }, [visible]);

  useEffect(() => {
    if (selectedTemplate) {
      fetchTemplateData(selectedTemplate.value);
    } else {
      setTemplateSteps([]);
      setTemplateVariables([]);
      setRequiredSecrets([]);
    }
  }, [selectedTemplate]);

  const fetchTemplates = async () => {
    setLoading(true);
    try {
      const data = await api.get('templates');
      setTemplates(data.templates || []);
    } catch (error) {
      console.error('Failed to fetch templates:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchTemplateData = async (templateId: string) => {
    setLoadingSteps(true);
    try {
      const [stepsData, variablesData] = await Promise.all([
        api.get(`templates/${templateId}/steps`),
        api.get(`templates/${templateId}/variables`)
      ]);
      
      const steps = stepsData.steps || [];
      const variables = variablesData.variables || [];
      
      console.log('Template steps:', steps);
      console.log('Template variables:', variables);
      
      setTemplateSteps(steps);
      setTemplateVariables(variables);
      
      // Extract required secrets from steps
      const secrets: string[] = steps
        .filter((step: any) => step.step_type === 'secret' && step.secret_key)
        .map((step: any) => step.secret_key as string);
      setRequiredSecrets(Array.from(new Set(secrets))); // Remove duplicates
      
      console.log('Required secrets:', secrets);
    } catch (error) {
      console.error('Failed to fetch template data:', error);
    } finally {
      setLoadingSteps(false);
    }
  };

  const handleImport = async () => {
    if (!selectedTemplate) return;

    setImporting(true);
    try {
      await api.post(`usecase/${usecaseId}/import-template`, {
        template_id: selectedTemplate.value,
        insert_position: parseInt(insertPosition.value)
      });

      setSelectedTemplate(null);
      setTemplateSteps([]);
      setInsertPosition({ label: 'At the end', value: '-1' });
      onSuccess();
    } catch (error) {
      console.error('Failed to import template:', error);
    } finally {
      setImporting(false);
    }
  };

  const selectedTemplateData = templates.find(t => t.id === selectedTemplate?.value);

  return (
    <Modal
      visible={visible}
      onDismiss={onDismiss}
      size="large"
      header="Import Template"
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={onDismiss}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleImport}
              disabled={!selectedTemplate || importing}
              loading={importing}
            >
              Import Template
            </Button>
          </SpaceBetween>
        </Box>
      }
    >
      <SpaceBetween direction="vertical" size="l">
        <FormField label="Select Template" description="Choose a template to import">
          <Select
            selectedOption={selectedTemplate}
            onChange={({ detail }) => setSelectedTemplate(detail.selectedOption)}
            options={templates.map(t => ({
              label: t.name,
              value: t.id,
              description: t.description
            }))}
            placeholder="Choose a template"
            loadingText="Loading templates..."
            statusType={loading ? 'loading' : 'finished'}
            empty="No templates available"
          />
        </FormField>

        {selectedTemplateData && (
          <Container>
            <SpaceBetween direction="vertical" size="s">
              <div>
                <Box variant="awsui-key-label">Description</Box>
                <div>{selectedTemplateData.description || '-'}</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Category</Box>
                <div>{selectedTemplateData.category || '-'}</div>
              </div>
              {selectedTemplateData.tags && selectedTemplateData.tags.length > 0 && (
                <div>
                  <Box variant="awsui-key-label">Tags</Box>
                  <SpaceBetween direction="horizontal" size="xs">
                    {selectedTemplateData.tags.map((tag: string) => (
                      <Badge key={tag}>{tag}</Badge>
                    ))}
                  </SpaceBetween>
                </div>
              )}
            </SpaceBetween>
          </Container>
        )}

        {selectedTemplate && (
          <>
            {requiredSecrets.length > 0 && (
              <Alert type="warning" header="Required Secrets">
                This template requires the following secrets to be configured in your use case:
                <ul style={{ marginTop: '8px', marginBottom: '0' }}>
                  {requiredSecrets.map(secret => (
                    <li key={secret}><strong>{secret}</strong></li>
                  ))}
                </ul>
              </Alert>
            )}

            {templateVariables.length > 0 && (
              <Container
                header={
                  <Header variant="h3">
                    Template Variables ({templateVariables.length})
                  </Header>
                }
              >
                <SpaceBetween direction="vertical" size="xs">
                  {templateVariables.map(variable => (
                    <Box key={variable.key} padding="xs">
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <Box variant="code">{variable.key}</Box>
                        {variable.value && (
                          <span style={{ color: '#5f6b7a' }}>= {variable.value}</span>
                        )}
                      </div>
                    </Box>
                  ))}
                </SpaceBetween>
              </Container>
            )}

            <FormField label="Insert Position" description="Where to insert the template steps">
              <Select
                selectedOption={insertPosition}
                onChange={({ detail }) => setInsertPosition(detail.selectedOption)}
                options={[
                  { label: 'At the beginning', value: '0' },
                  { label: 'At the end', value: '-1' }
                ]}
              />
            </FormField>

            <Container
              header={
                <Header variant="h3">
                  Template Steps Preview ({templateSteps.length})
                </Header>
              }
            >
              {loadingSteps ? (
                <Box textAlign="center" padding="l">
                  <Spinner />
                </Box>
              ) : templateSteps.length > 0 ? (
                <SpaceBetween direction="vertical" size="xs">
                  {templateSteps.map((step: any, index) => (
                    <Box key={step.id} padding="s" variant="div">
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
                        <Badge>{index + 1}</Badge>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: 500 }}>{step.instruction}</div>
                          <div style={{ fontSize: '0.85em', color: '#5f6b7a', marginTop: '4px' }}>
                            Type: {step.step_type}
                            {step.step_type === 'secret' && step.secret_key && (
                              <span style={{ marginLeft: '8px' }}>
                                <Badge color="red">
                                  Requires secret: {step.secret_key}
                                </Badge>
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </Box>
                  ))}
                </SpaceBetween>
              ) : (
                <Box textAlign="center" padding="l">
                  No steps in this template
                </Box>
              )}
            </Container>
          </>
        )}
      </SpaceBetween>
    </Modal>
  );
}
