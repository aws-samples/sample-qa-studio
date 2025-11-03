import React, { useState } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import Button from "@cloudscape-design/components/button";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Toggle from "@cloudscape-design/components/toggle";
import StepsTable from '../StepsTable';
import WorkflowStepsCard from '../WorkflowStepsCard';
import StepFormModal from './StepFormModal';
import { api } from '../../utils/api';
import { useMultipleAsyncData } from '../common/useAsyncData';
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

export default function WorkflowSteps({ usecaseId }: WorkflowStepsProps) {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [useCardLayout, setUseCardLayout] = useState(true);

  const { data, loading, refetch } = useMultipleAsyncData({
    steps: () => api.get(`usecase/${usecaseId}/steps`)
  }, [usecaseId]);

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
      />

      <SpaceBetween direction='vertical' size="m">
        <Header
          variant="h1"
          actions={
            <SpaceBetween direction="horizontal" size="xs">
              <Toggle
                checked={useCardLayout}
                onChange={({ detail }) => setUseCardLayout(detail.checked)}
              >
                Card Layout
              </Toggle>
              <Button onClick={() => setShowCreateModal(true)}>
                Add Step
              </Button>
            </SpaceBetween>
          }
        />
      
        {useCardLayout ? (
          <WorkflowStepsCard
            steps={steps}
            onReorder={handleReorderSteps}
            onUpdateStep={handleUpdateStep}
            onDeleteStep={handleDeleteStep}
            onAddStep={handleCreateStep}
            usecaseId={usecaseId}
          />
        ) : (
          <StepsTable
            steps={steps}
            onStepsReordered={refreshSteps}
            onUpdateStep={handleUpdateStep}
            onDeleteStep={handleDeleteStep}
            usecaseId={usecaseId}
          />
        )}
      </SpaceBetween>
    </>
  );
}