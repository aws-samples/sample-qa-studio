import Container from "@cloudscape-design/components/container";
import SpaceBetween from "@cloudscape-design/components/space-between";
import FormField from "@cloudscape-design/components/form-field";
import Input from "@cloudscape-design/components/input";
import ColumnLayout from "@cloudscape-design/components/column-layout";
import Badge from "@cloudscape-design/components/badge";
import type { StepProps, UsecaseDetail } from '../types';
import { fetchUsecaseDetail } from '../sourceDetail';
import { PreviewField, PreviewTags, SourcePicker, useSourceDetail, useSourceList, type SourceItem } from './SourcePicker';

function UsecasePreview({ detail }: { detail: UsecaseDetail }) {
  return (
    <ColumnLayout columns={2} variant="text-grid">
      <PreviewField label="Name">{detail.name}</PreviewField>
      <PreviewField label="Status">
        {detail.active ? <Badge color="green">Active</Badge> : <Badge color="red">Inactive</Badge>}
      </PreviewField>
      <PreviewField label="Starting URL">{detail.starting_url || '-'}</PreviewField>
      <PreviewField label="Steps">{detail.steps?.length || 0} step(s)</PreviewField>
      <PreviewField label="Variables">{detail.variables?.length || 0} variable(s)</PreviewField>
      <PreviewField label="Headers">{Object.keys(detail.headers || {}).length} header(s)</PreviewField>
      <PreviewTags tags={detail.tags || []} />
      {detail.description && (
        <PreviewField label="Description" wide>
          {detail.description}
        </PreviewField>
      )}
    </ColumnLayout>
  );
}

export default function SelectSourceStep({ state, dispatch, validationErrors }: StepProps) {
  const { cloneConfig } = state;
  const usecases = useSourceList<SourceItem>('usecases', 'usecases', 'Failed to load use cases. Please try again.');
  const loadingDetail = useSourceDetail(cloneConfig.selectedUsecaseId, fetchUsecaseDetail, (detail) =>
    dispatch({
      type: 'UPDATE_CLONE_CONFIG',
      payload: {
        usecaseDetail: detail,
        newName: cloneConfig.newName || `${detail.name} (Copy)`,
      },
    }),
  );

  return (
    <SpaceBetween direction="vertical" size="l">
      <SourcePicker
        items={usecases.items}
        loading={usecases.loading}
        fetchError={usecases.error}
        onDismissError={usecases.dismissError}
        selectedId={cloneConfig.selectedUsecaseId}
        onSelect={(usecase) =>
          dispatch({
            type: 'UPDATE_CLONE_CONFIG',
            payload: {
              selectedUsecaseId: usecase?.id || null,
              usecaseDetail: null,
              newName: usecase ? `${usecase.name} (Copy)` : '',
            },
          })
        }
        errorText={validationErrors.selectedUsecaseId}
        loadingDetail={loadingDetail}
        preview={cloneConfig.usecaseDetail ? <UsecasePreview detail={cloneConfig.usecaseDetail} /> : null}
        labels={{
          label: 'Select use case to clone',
          description: 'Choose an existing use case to create a copy from',
          placeholder: 'Choose a use case',
          loadingText: 'Loading use cases...',
          empty: 'No use cases available.',
          previewTitle: 'Use case summary',
        }}
      />

      {cloneConfig.selectedUsecaseId && (
        <Container>
          <FormField
            label="New use case name"
            description="Name for the cloned use case"
          >
            <Input
              value={cloneConfig.newName}
              onChange={({ detail }) =>
                dispatch({
                  type: 'UPDATE_CLONE_CONFIG',
                  payload: { newName: detail.value },
                })
              }
              placeholder="Enter name for the cloned use case"
            />
          </FormField>
        </Container>
      )}
    </SpaceBetween>
  );
}
