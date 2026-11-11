import React, { useState } from 'react';
import Header from "@cloudscape-design/components/header";
import Button from "@cloudscape-design/components/button";
import SpaceBetween from "@cloudscape-design/components/space-between";
import WorkflowStepsCard from '../WorkflowStepsCard';
import StepFormModal from './StepFormModal';
import ImportTemplateModal from '../templates/ImportTemplateModal';
import { api, datasetsApi, type ApplicationDatasetSummary } from '../../utils/api';
import { useApiData, useMultipleAsyncData } from '../common/useAsyncData';
import { ContainerLoading } from '../common/LoadingStates';

interface UsecaseStep {
  pk: string;
  sk: string;
  usecaseId: string;
  sort: number;
  instruction: string;
  step_type?: string;
  secret_key?: string;
  validation_type?: string;
  validation_operator?: string;
  validation_value?: string;
  assertion_variable?: string;
}

interface WorkflowStepsProps {
  usecaseId: string;
}

/** The owning application's datasets, offered as repeat-step sources. */
interface ApplicationDatasets {
  applicationId?: string;
  datasets: ApplicationDatasetSummary[];
}

const NO_APPLICATION_DATASETS: ApplicationDatasets = { datasets: [] };

export default function WorkflowSteps({ usecaseId }: WorkflowStepsProps) {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);

  const { data, loading, refetch } = useMultipleAsyncData({
    steps: () => api.get(`usecase/${usecaseId}/steps`)
  }, [usecaseId]);

  // Loaded once per use case (not on every step refetch): the use case
  // definition names the application, whose dataset list names dataset_id
  // repeats in the views and fills the modal's Application dataset select.
  const { data: applicationDatasets } = useApiData<ApplicationDatasets>(async () => {
    const usecase = await api.get(`usecase/${usecaseId}`);
    const applicationId: string | undefined = usecase?.application_id || undefined;
    if (!applicationId) return NO_APPLICATION_DATASETS;
    try {
      const { datasets } = await datasetsApi.list(applicationId);
      return { applicationId, datasets };
    } catch (error) {
      console.error(`Failed to load datasets of application ${applicationId}:`, error);
      return { applicationId, datasets: [] };
    }
  }, [usecaseId]);
  const { applicationId, datasets } = applicationDatasets ?? NO_APPLICATION_DATASETS;

  const steps = data.steps?.steps || [];

  const refreshSteps = async () => {
    await refetch();
  };

  const handleCreateStep = async (stepData: any, position?: number) => {
    if (position !== undefined && position <= steps.length) {
      // Inserting in the middle - need to shift existing steps first
      // Shift all steps at position and above up by 1
      const stepsToShift = steps
        .filter(step => step.sort >= position)
        .map(step => ({
          step_id: step.sk,
          sort: step.sort + 1
        }));
      
      if (stepsToShift.length > 0) {
        await api.patch(`usecase/${usecaseId}/steps/reorder`, {
          step_orders: stepsToShift
        });
      }
      
      // Now create the new step at the desired position
      const fullStepData = {
        usecaseId: usecaseId,
        sort: position,
        ...stepData
      };
      
      await api.post(`usecase/${usecaseId}/steps`, fullStepData);
      await refreshSteps();
    } else {
      // Adding at the end
      const insertPosition = steps.length + 1;
      const fullStepData = {
        usecaseId: usecaseId,
        sort: insertPosition,
        ...stepData
      };
      
      await api.post(`usecase/${usecaseId}/steps`, fullStepData);
      await refreshSteps();
    }
  };

  const handleUpdateStep = async (stepData: any) => {
    const stepId = stepData.sk.replace("STEP#", "");
    await api.patch(`usecase/${usecaseId}/steps/${stepId}`, stepData);
    await refreshSteps();
  };

  const reorderStepsSequentially = async () => {
    try {
      const updatedSteps = await api.get(`usecase/${usecaseId}/steps`);
      const stepsToReorder = updatedSteps.steps || [];
      
      if (stepsToReorder.length > 0) {
        const stepOrders = stepsToReorder
          .sort((a, b) => a.sort - b.sort)
          .map((step, index) => ({
            step_id: step.sk,
            sort: index + 1
          }));
        
        await api.patch(`usecase/${usecaseId}/steps/reorder`, {
          step_orders: stepOrders
        });
        
        await refreshSteps();
      }
    } catch (error) {
      console.error('Failed to reorder steps:', error);
    }
  };

  const handleDeleteStep = async (stepId: string) => {
    try {
      await api.delete(`usecase/${usecaseId}/steps/${stepId.replace("STEP#", "")}`);
      await reorderStepsSequentially();
    } catch (error) {
      console.error('Failed to delete step:', error);
    }
  };

  const handleReorderSteps = async (reorderedSteps: UsecaseStep[]) => {
    try {
      const stepOrders = reorderedSteps.map((step) => ({
        step_id: step.sk,
        sort: step.sort
      }));

      await api.patch(`usecase/${usecaseId}/steps/reorder`, {
        step_orders: stepOrders
      });

      await refreshSteps();
    } catch (error) {
      console.error('Failed to reorder steps:', error);
      throw error;
    }
  };

  const handleUpdateFromTemplate = async (stepId: string) => {
    try {
      await api.post(`usecase/${usecaseId}/steps/${stepId}/update-from-template`);
      await refreshSteps();
    } catch (error) {
      console.error('Failed to update step from template:', error);
      throw error;
    }
  };

  if (loading) {
    return (
      <ContainerLoading 
        title="Workflow Steps"
        text="Loading workflow steps..."
      />
    );
  }

  return (
    <>
      <StepFormModal
        visible={showCreateModal}
        onDismiss={() => setShowCreateModal(false)}
        onSubmit={handleCreateStep}
        usecaseId={usecaseId}
        title="Create New Step"
        existingSteps={steps}
        applicationId={applicationId}
        datasets={datasets}
      />

      <ImportTemplateModal
        visible={showImportModal}
        usecaseId={usecaseId}
        onDismiss={() => setShowImportModal(false)}
        onSuccess={() => {
          setShowImportModal(false);
          refreshSteps();
        }}
      />

      <SpaceBetween direction='vertical' size="m">
        <Header
          variant="h1"
          actions={
            <SpaceBetween direction="horizontal" size="xs">
              <Button onClick={() => setShowImportModal(true)} iconName="download">
                Import Template
              </Button>
              <Button onClick={() => setShowCreateModal(true)} variant="primary">
                Add Step
              </Button>
            </SpaceBetween>
          }
        />
      
        <WorkflowStepsCard
          steps={steps}
          onReorder={handleReorderSteps}
          onUpdateStep={handleUpdateStep}
          onDeleteStep={handleDeleteStep}
          onAddStep={handleCreateStep}
          onUpdateFromTemplate={handleUpdateFromTemplate}
          usecaseId={usecaseId}
          applicationId={applicationId}
          datasets={datasets}
        />
      </SpaceBetween>
    </>
  );
}