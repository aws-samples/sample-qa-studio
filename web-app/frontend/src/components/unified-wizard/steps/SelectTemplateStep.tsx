import SpaceBetween from "@cloudscape-design/components/space-between";
import ColumnLayout from "@cloudscape-design/components/column-layout";
import type { StepProps, TemplateDetail } from '../types';
import { fetchTemplateDetail } from '../sourceDetail';
import { PreviewField, PreviewTags, SourcePicker, useSourceDetail, useSourceList, type SourceItem } from './SourcePicker';

function TemplatePreview({ detail }: { detail: TemplateDetail }) {
  return (
    <ColumnLayout columns={2} variant="text-grid">
      <PreviewField label="Template Name">{detail.name}</PreviewField>
      <PreviewField label="Starting URL">{detail.starting_url || '-'}</PreviewField>
      <PreviewField label="Steps">{detail.steps?.length || 0} step(s)</PreviewField>
      <PreviewField label="Variables">{detail.variables?.length || 0} variable(s)</PreviewField>
      {/* The "template" marker tag says nothing here. */}
      <PreviewTags tags={(detail.tags || []).filter((tag) => tag.toLowerCase() !== 'template')} />
      {detail.description && (
        <PreviewField label="Description" wide>
          {detail.description}
        </PreviewField>
      )}
    </ColumnLayout>
  );
}

export default function SelectTemplateStep({ state, dispatch, validationErrors }: StepProps) {
  const { templateConfig } = state;
  const templates = useSourceList<SourceItem>('templates', 'templates', 'Failed to load templates. Please try again.');
  const loadingDetail = useSourceDetail(templateConfig.selectedTemplateId, fetchTemplateDetail, (detail) =>
    dispatch({
      type: 'UPDATE_TEMPLATE_CONFIG',
      payload: {
        templateDetail: detail,
        startingUrl: detail.starting_url || '',
        description: detail.description || '',
      },
    }),
  );

  return (
    <SpaceBetween direction="vertical" size="l">
      <SourcePicker
        items={templates.items}
        loading={templates.loading}
        fetchError={templates.error}
        onDismissError={templates.dismissError}
        selectedId={templateConfig.selectedTemplateId}
        onSelect={(template) =>
          dispatch({
            type: 'UPDATE_TEMPLATE_CONFIG',
            payload: {
              selectedTemplateId: template?.id || null,
              templateDetail: null,
            },
          })
        }
        errorText={validationErrors.selectedTemplateId}
        loadingDetail={loadingDetail}
        preview={templateConfig.templateDetail ? <TemplatePreview detail={templateConfig.templateDetail} /> : null}
        labels={{
          label: 'Template',
          description: 'Choose a pre-built template to start from',
          placeholder: 'Choose a template',
          loadingText: 'Loading templates...',
          empty: "No templates available. Create a use case and tag it with 'template' to make it available here.",
          previewTitle: 'Template preview',
        }}
      />
    </SpaceBetween>
  );
}
