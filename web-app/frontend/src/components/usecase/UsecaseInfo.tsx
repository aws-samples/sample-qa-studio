import React, { useState } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import Button from "@cloudscape-design/components/button";
import KeyValuePairs from "@cloudscape-design/components/key-value-pairs";
import CopyToClipboard from "@cloudscape-design/components/copy-to-clipboard";
import Link from "@cloudscape-design/components/link";
import Badge from "@cloudscape-design/components/badge";
import EditUsecaseForm from './EditUsecaseForm';
import { api } from '../../utils/api';
import { useApiData } from '../common/useAsyncData';
import { ContainerLoading, EmptyState } from '../common/LoadingStates';
import { regionOptions } from '../../utils/browser_regions';

interface UsecaseInfoProps {
  usecaseId: string;
}

export default function UsecaseInfo({ usecaseId }: UsecaseInfoProps) {
  const [editingUsecase, setEditingUsecase] = useState(false);

  const { data: usecase, loading, setData: setUsecase } = useApiData(
    () => api.get(`usecase/${usecaseId}`),
    [usecaseId]
  );

  const handleSave = async (updatedUsecase: any) => {
    try {
      await api.patch(`usecase/${usecaseId}`, updatedUsecase);
      setUsecase({ ...usecase, ...updatedUsecase });
      setEditingUsecase(false);
    } catch (error) {
      console.error('Failed to update usecase:', error);
    }
  };

  if (loading) {
    return (
      <ContainerLoading 
        title="Use Case Information"
        text="Loading usecase information..."
      />
    );
  }

  if (!usecase) {
    return (
      <Container
        header={<Header variant="h2">Use Case Information</Header>}
      >
        <EmptyState 
          title="Usecase not found"
          message="The requested usecase could not be found."
        />
      </Container>
    );
  }

  return (
    <Container
      header={
        <Header
          variant="h2"
          actions={
            <Button onClick={() => setEditingUsecase(!editingUsecase)}>
              {editingUsecase ? 'Cancel' : 'Edit'}
            </Button>
          }
        >
          Use Case Information
        </Header>
      }
    >
      {editingUsecase ? (
        <EditUsecaseForm
          usecase={usecase}
          onSave={handleSave}
          onCancel={() => setEditingUsecase(false)}
        />
      ) : (
        <KeyValuePairs
          columns={3}
          items={[
            {
              label: "Name",
              value: usecase.name,
            },
            {
              label: "ID",
              value: (
                <CopyToClipboard
                  copyButtonAriaLabel="Copy ID"
                  copyErrorText="ID failed to copy"
                  copySuccessText="ID copied"
                  textToCopy={usecase.id}
                  variant="inline"
                />
              ),
            },
            {
              label: "Description",
              value: usecase.description,
            },
            {
              label: "Active",
              value: usecase.active ? (
                <Badge color="green">Active</Badge>
              ) : (
                <Badge color="red">Inactive</Badge>
              ),
            },
            {
              label: "Execution Region",
              value: usecase.executing_region,
            },
            ...(usecase.test_platform === 'mobile' ? [
              {
                label: "Test Platform",
                value: <Badge color="blue">Mobile</Badge>,
              },
              {
                label: "Mobile Platform",
                value: usecase.platform || '-',
              },
              ...(usecase.platform === 'ANDROID' ? [
                { label: "App Package", value: usecase.app_package || '-' },
                { label: "App Activity", value: usecase.app_activity || '-' },
              ] : []),
              ...(usecase.platform === 'IOS' ? [
                { label: "Bundle ID", value: usecase.bundle_id || '-' },
              ] : []),
              {
                label: "App Binary",
                value: usecase.app_binary_s3_path
                  ? usecase.app_binary_s3_path.split('/').pop()
                  : <Badge color="red">Not uploaded</Badge>,
              },
            ] : [
              {
                label: "Starting URL",
                value: (
                  <Link external href={usecase.starting_url}>
                    {usecase.starting_url}
                  </Link>
                ),
              },
            ]),
            {
              label: "Created",
              value: new Date(usecase.created_at).toLocaleDateString(),
            },
            {
              label: "Tags",
              value: usecase.tags?.length > 0 ? usecase.tags.join(', ') : 'No tags',
            },
          ]}
        />
      )}
    </Container>
  );
}