import { useState, useEffect } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import FormField from "@cloudscape-design/components/form-field";
import Select, { SelectProps } from "@cloudscape-design/components/select";
import Box from "@cloudscape-design/components/box";
import ColumnLayout from "@cloudscape-design/components/column-layout";
import Badge from "@cloudscape-design/components/badge";
import Spinner from "@cloudscape-design/components/spinner";
import Alert from "@cloudscape-design/components/alert";
import type { StepProps, TemplateDetail } from '../types';
import { api } from '../../../utils/api';

interface Template {
  id: string;
  name: string;
  description: string;
  starting_url?: string;
  active?: boolean;
  tags?: string[];
}

export default function SelectTemplateStep({ state, dispatch, validationErrors }: StepProps) {
  const { templateConfig } = state;
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Fetch templates on mount
  useEffect(() => {
    const fetchTemplates = async () => {
      setLoading(true);
      setFetchError(null);
      try {
        const data = await api.get('templates');
        setTemplates(data.templates || []);
      } catch (error: any) {
        console.error('Failed to fetch templates:', error);
        setFetchError(error.message || 'Failed to load templates. Please try again.');
      } finally {
        setLoading(false);
      }
    };

    fetchTemplates();
  }, []);

  // Fetch template detail when selection changes
  useEffect(() => {
    const fetchTemplateDetail = async () => {
      if (!templateConfig.selectedTemplateId) {
        return;
      }

      setLoadingDetail(true);
      try {
        const [templateData, stepsData, variablesData] = await Promise.all([
          api.get(`templates/${templateConfig.selectedTemplateId}`),
          api.get(`templates/${templateConfig.selectedTemplateId}/steps`),
          api.get(`templates/${templateConfig.selectedTemplateId}/variables`).catch(() => ({ variables: [] })),
        ]);

        const detail: TemplateDetail = {
          ...templateData,
          steps: stepsData.steps || [],
          variables: variablesData.variables || [],
        };

        dispatch({
          type: 'UPDATE_TEMPLATE_CONFIG',
          payload: {
            templateDetail: detail,
            startingUrl: detail.starting_url || '',
            description: detail.description || '',
          },
        });
      } catch (error: any) {
        console.error('Failed to fetch template detail:', error);
      } finally {
        setLoadingDetail(false);
      }
    };

    fetchTemplateDetail();
  }, [templateConfig.selectedTemplateId]); // eslint-disable-line react-hooks/exhaustive-deps

  const templateOptions: SelectProps.Option[] = templates.map((t) => ({
    label: t.name,
    value: t.id,
    description: t.description,
  }));

  const selectedOption = templateConfig.selectedTemplateId
    ? templateOptions.find((opt) => opt.value === templateConfig.selectedTemplateId) || null
    : null;

  const handleTemplateChange = (option: SelectProps.Option | null) => {
    dispatch({
      type: 'UPDATE_TEMPLATE_CONFIG',
      payload: {
        selectedTemplateId: option?.value || null,
        templateDetail: null,
      },
    });
  };

  return (
    <SpaceBetween direction="vertical" size="l">
      {fetchError && (
        <Alert type="error" dismissible onDismiss={() => setFetchError(null)}>
          {fetchError}
        </Alert>
      )}

      <Container>
        <FormField
          label="Template"
          description="Choose a pre-built template to start from"
          errorText={validationErrors.selectedTemplateId}
        >
          <Select
            selectedOption={selectedOption}
            onChange={({ detail }) => handleTemplateChange(detail.selectedOption)}
            options={templateOptions}
            placeholder="Choose a template"
            loadingText="Loading templates..."
            statusType={loading ? 'loading' : 'finished'}
            disabled={loading}
            filteringType="auto"
            empty="No templates available. Create a use case and tag it with 'template' to make it available here."
          />
        </FormField>
      </Container>

      {templateConfig.selectedTemplateId && (
        <Container header={<Header variant="h2">Template preview</Header>}>
          {loadingDetail ? (
            <Box textAlign="center" padding="l">
              <Spinner />
            </Box>
          ) : templateConfig.templateDetail ? (
            <ColumnLayout columns={2} variant="text-grid">
              <div>
                <Box variant="awsui-key-label">Template Name</Box>
                <div>{templateConfig.templateDetail.name}</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Starting URL</Box>
                <div>{templateConfig.templateDetail.starting_url || '-'}</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Steps</Box>
                <div>{templateConfig.templateDetail.steps?.length || 0} step(s)</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Variables</Box>
                <div>{templateConfig.templateDetail.variables?.length || 0} variable(s)</div>
              </div>
              {templateConfig.templateDetail.tags && templateConfig.templateDetail.tags.length > 0 && (
                <div>
                  <Box variant="awsui-key-label">Tags</Box>
                  <SpaceBetween direction="horizontal" size="xs">
                    {templateConfig.templateDetail.tags
                      .filter((tag) => tag.toLowerCase() !== 'template')
                      .map((tag) => (
                        <Badge key={tag}>{tag}</Badge>
                      ))}
                  </SpaceBetween>
                </div>
              )}
              {templateConfig.templateDetail.description && (
                <div style={{ gridColumn: '1 / -1' }}>
                  <Box variant="awsui-key-label">Description</Box>
                  <div>{templateConfig.templateDetail.description}</div>
                </div>
              )}
            </ColumnLayout>
          ) : null}
        </Container>
      )}
    </SpaceBetween>
  );
}
