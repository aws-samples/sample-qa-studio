import { useState, useEffect } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import FormField from "@cloudscape-design/components/form-field";
import Select, { SelectProps } from "@cloudscape-design/components/select";
import Input from "@cloudscape-design/components/input";
import Box from "@cloudscape-design/components/box";
import ColumnLayout from "@cloudscape-design/components/column-layout";
import Badge from "@cloudscape-design/components/badge";
import Spinner from "@cloudscape-design/components/spinner";
import Alert from "@cloudscape-design/components/alert";
import type { StepProps, UsecaseDetail } from '../types';
import { api } from '../../../utils/api';

interface Usecase {
  id: string;
  name: string;
  description: string;
  starting_url?: string;
  active?: boolean;
  tags?: string[];
}

export default function SelectSourceStep({ state, dispatch, validationErrors }: StepProps) {
  const { cloneConfig } = state;
  const [usecases, setUsecases] = useState<Usecase[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Fetch usecases on mount
  useEffect(() => {
    const fetchUsecases = async () => {
      setLoading(true);
      setFetchError(null);
      try {
        const data = await api.get('usecases');
        setUsecases(data.usecases || []);
      } catch (error: any) {
        console.error('Failed to fetch usecases:', error);
        setFetchError(error.message || 'Failed to load use cases. Please try again.');
      } finally {
        setLoading(false);
      }
    };

    fetchUsecases();
  }, []);

  // Fetch usecase detail when selection changes
  useEffect(() => {
    const fetchUsecaseDetail = async () => {
      if (!cloneConfig.selectedUsecaseId) {
        return;
      }

      setLoadingDetail(true);
      try {
        const [usecaseData, stepsData, variablesData, headersData] = await Promise.all([
          api.get(`usecase/${cloneConfig.selectedUsecaseId}`),
          api.get(`usecase/${cloneConfig.selectedUsecaseId}/steps`),
          api.get(`usecase/${cloneConfig.selectedUsecaseId}/variables`).catch(() => ({ variables: [] })),
          api.get(`usecase/${cloneConfig.selectedUsecaseId}/headers`).catch(() => ({ headers: {} })),
        ]);

        const detail: UsecaseDetail = {
          ...usecaseData,
          steps: stepsData.steps || [],
          variables: variablesData.variables || [],
          headers: headersData.headers || {},
        };

        dispatch({
          type: 'UPDATE_CLONE_CONFIG',
          payload: {
            usecaseDetail: detail,
            newName: cloneConfig.newName || `${detail.name} (Copy)`,
          },
        });
      } catch (error: any) {
        console.error('Failed to fetch usecase detail:', error);
      } finally {
        setLoadingDetail(false);
      }
    };

    fetchUsecaseDetail();
  }, [cloneConfig.selectedUsecaseId]); // eslint-disable-line react-hooks/exhaustive-deps

  const usecaseOptions: SelectProps.Option[] = usecases.map((uc) => ({
    label: uc.name,
    value: uc.id,
    description: uc.description,
  }));

  const selectedOption = cloneConfig.selectedUsecaseId
    ? usecaseOptions.find((opt) => opt.value === cloneConfig.selectedUsecaseId) || null
    : null;

  const handleUsecaseChange = (option: SelectProps.Option | null) => {
    const original = usecases.find((uc) => uc.id === option?.value);
    dispatch({
      type: 'UPDATE_CLONE_CONFIG',
      payload: {
        selectedUsecaseId: option?.value || null,
        usecaseDetail: null,
        newName: original ? `${original.name} (Copy)` : '',
      },
    });
  };

  return (
    <SpaceBetween direction="vertical" size="l">
      <Container>
        <SpaceBetween direction="vertical" size="l">
          {fetchError && (
            <Alert type="error" dismissible onDismiss={() => setFetchError(null)}>
              {fetchError}
            </Alert>
          )}

          <FormField
            label="Select use case to clone"
            description="Choose an existing use case to create a copy from"
            errorText={validationErrors.selectedUsecaseId}
          >
            <Select
              selectedOption={selectedOption}
              onChange={({ detail }) => handleUsecaseChange(detail.selectedOption)}
              options={usecaseOptions}
              placeholder="Choose a use case"
              loadingText="Loading use cases..."
              statusType={loading ? 'loading' : 'finished'}
              disabled={loading}
              filteringType="auto"
              empty="No use cases available."
            />
          </FormField>
        </SpaceBetween>
      </Container>

      {cloneConfig.selectedUsecaseId && (
        <Container header={<Header variant="h2">Use case summary</Header>}>
          {loadingDetail ? (
            <Box textAlign="center" padding="l">
              <Spinner />
            </Box>
          ) : cloneConfig.usecaseDetail ? (
            <ColumnLayout columns={2} variant="text-grid">
              <div>
                <Box variant="awsui-key-label">Name</Box>
                <div>{cloneConfig.usecaseDetail.name}</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Status</Box>
                <div>
                  {cloneConfig.usecaseDetail.active ? (
                    <Badge color="green">Active</Badge>
                  ) : (
                    <Badge color="red">Inactive</Badge>
                  )}
                </div>
              </div>
              <div>
                <Box variant="awsui-key-label">Starting URL</Box>
                <div>{cloneConfig.usecaseDetail.starting_url || '-'}</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Steps</Box>
                <div>{cloneConfig.usecaseDetail.steps?.length || 0} step(s)</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Variables</Box>
                <div>{cloneConfig.usecaseDetail.variables?.length || 0} variable(s)</div>
              </div>
              <div>
                <Box variant="awsui-key-label">Headers</Box>
                <div>{Object.keys(cloneConfig.usecaseDetail.headers || {}).length} header(s)</div>
              </div>
              {cloneConfig.usecaseDetail.tags && cloneConfig.usecaseDetail.tags.length > 0 && (
                <div>
                  <Box variant="awsui-key-label">Tags</Box>
                  <SpaceBetween direction="horizontal" size="xs">
                    {cloneConfig.usecaseDetail.tags.map((tag) => (
                      <Badge key={tag}>{tag}</Badge>
                    ))}
                  </SpaceBetween>
                </div>
              )}
              {cloneConfig.usecaseDetail.description && (
                <div style={{ gridColumn: '1 / -1' }}>
                  <Box variant="awsui-key-label">Description</Box>
                  <div>{cloneConfig.usecaseDetail.description}</div>
                </div>
              )}
            </ColumnLayout>
          ) : null}
        </Container>
      )}

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
