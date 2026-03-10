import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import FormField from "@cloudscape-design/components/form-field";
import Select, { SelectProps } from "@cloudscape-design/components/select";
import Input from "@cloudscape-design/components/input";
import Textarea from "@cloudscape-design/components/textarea";
import Box from "@cloudscape-design/components/box";
import ColumnLayout from "@cloudscape-design/components/column-layout";
import Badge from "@cloudscape-design/components/badge";
import Spinner from "@cloudscape-design/components/spinner";
import BreadcrumbGroup from "@cloudscape-design/components/breadcrumb-group";
import { api } from '../utils/api';

interface Template {
  id: string;
  name: string;
  description: string;
  starting_url?: string;
  active?: boolean;
  tags?: string[];
}

interface TemplateDetail extends Template {
  steps?: any[];
  variables?: any[];
}

export default function CreateFromTemplate() {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<SelectProps.Option | null>(null);
  const [templateDetail, setTemplateDetail] = useState<TemplateDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [starting_url, setStartingUrl] = useState('');

  useEffect(() => {
    const fetchTemplates = async () => {
      try {
        const data = await api.get('templates');
        setTemplates(data.templates || []);
      } catch (error) {
        console.error('Failed to fetch templates:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchTemplates();
  }, []);

  useEffect(() => {
    const fetchTemplateDetail = async () => {
      if (!selectedTemplate?.value) {
        setTemplateDetail(null);
        return;
      }

      setLoadingDetail(true);
      try {
        const [templateData, stepsData, variablesData] = await Promise.all([
          api.get(`templates/${selectedTemplate.value}`),
          api.get(`templates/${selectedTemplate.value}/steps`),
          api.get(`templates/${selectedTemplate.value}/variables`).catch(() => ({ variables: [] }))
        ]);
        
        setTemplateDetail({
          ...templateData,
          steps: stepsData.steps || [],
          variables: variablesData.variables || []
        });
      } catch (error) {
        console.error('Failed to fetch template detail:', error);
      } finally {
        setLoadingDetail(false);
      }
    };

    fetchTemplateDetail();
  }, [selectedTemplate]);

  const handleCreate = async () => {
    if (!selectedTemplate || !name.trim()) return;

    setCreating(true);
    try {
      const response = await api.post(`templates/${selectedTemplate.value}/apply`, {
        name,
        description,
        starting_url
      });
      
      if (response.usecaseId) {
        navigate(`/usecase/${response.usecaseId}`);
      }
    } catch (error) {
      console.error('Failed to create from template:', error);
    } finally {
      setCreating(false);
    }
  };

  const templateOptions: SelectProps.Option[] = templates.map(t => ({
    label: t.name,
    value: t.id,
    description: t.description
  }));

  return (
    <SpaceBetween direction="vertical" size="l">
      <BreadcrumbGroup
        items={[
          { text: 'Home', href: '/' },
          { text: 'Create Use Case', href: '/create' },
          { text: 'Start from Template', href: '/create/template' }
        ]}
        onFollow={(event) => {
          event.preventDefault();
          navigate(event.detail.href);
        }}
      />

      <Header
        variant="h1"
        description="Begin with a pre-built template and add your own steps and configurations."
      >
        Start from Template
      </Header>

      <Container>
        <SpaceBetween direction="vertical" size="l">
          <FormField label="Select Template">
            <Select
              selectedOption={selectedTemplate}
              onChange={({ detail }) => {
                setSelectedTemplate(detail.selectedOption);
                if (detail.selectedOption) {
                  const template = templates.find(t => t.id === detail.selectedOption.value);
                  if (template) {
                    setName('');
                    setDescription(template.description || '');
                    setStartingUrl('');
                  }
                }
              }}
              options={templateOptions}
              placeholder="Choose a template"
              loadingText="Loading templates..."
              statusType={loading ? 'loading' : 'finished'}
              disabled={loading || creating}
              filteringType="auto"
              empty="No templates available. Create a use case and tag it with 'template' to make it available here."
            />
          </FormField>
        </SpaceBetween>
      </Container>

      {selectedTemplate && (
        <Container header={<Header variant="h2">Template Summary</Header>}>
          {loadingDetail ? (
            <Box textAlign="center" padding="l">
              <Spinner />
            </Box>
          ) : templateDetail ? (
            <ColumnLayout columns={2} variant="text-grid">
              <div>
                <Box variant="awsui-key-label">Template Name</Box>
                <div>{templateDetail.name}</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Starting URL</Box>
                <div>{templateDetail.starting_url || '-'}</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Steps</Box>
                <div>{templateDetail.steps?.length || 0} step(s)</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Variables</Box>
                <div>{templateDetail.variables?.length || 0} variable(s)</div>
              </div>
              {templateDetail.tags && templateDetail.tags.length > 0 && (
                <div>
                  <Box variant="awsui-key-label">Tags</Box>
                  <SpaceBetween direction="horizontal" size="xs">
                    {templateDetail.tags.filter(tag => tag.toLowerCase() !== 'template').map(tag => (
                      <Badge key={tag}>{tag}</Badge>
                    ))}
                  </SpaceBetween>
                </div>
              )}
              {templateDetail.description && (
                <div style={{ gridColumn: '1 / -1' }}>
                  <Box variant="awsui-key-label">Description</Box>
                  <div>{templateDetail.description}</div>
                </div>
              )}
            </ColumnLayout>
          ) : null}
        </Container>
      )}

      {selectedTemplate && (
        <Container>
          <SpaceBetween direction="vertical" size="l">
            <FormField label="Use Case Name" description="Name for your new use case">
              <Input
                value={name}
                onChange={({ detail }) => setName(detail.value)}
                placeholder="Enter use case name"
                disabled={!selectedTemplate || creating}
              />
            </FormField>

            <FormField label="Description" description="Describe what this use case will test">
              <Textarea
                value={description}
                onChange={({ detail }) => setDescription(detail.value)}
                placeholder="Enter use case description"
                rows={4}
                disabled={!selectedTemplate || creating}
              />
            </FormField>

            <FormField label="Starting URL" description="The URL where the test will begin">
              <Input
                value={starting_url}
                onChange={({ detail }) => setStartingUrl(detail.value)}
                placeholder="https://example.com"
                disabled={!selectedTemplate || creating}
              />
            </FormField>

            <SpaceBetween direction="horizontal" size="xs">
              <Button
                variant="primary"
                onClick={handleCreate}
                loading={creating}
                disabled={!selectedTemplate || !name.trim() || !starting_url.trim() || creating}
              >
                Create
              </Button>
              <Button
                onClick={() => navigate('/create')}
                disabled={creating}
              >
                Cancel
              </Button>
            </SpaceBetween>
          </SpaceBetween>
        </Container>
      )}
    </SpaceBetween>
  );
}
