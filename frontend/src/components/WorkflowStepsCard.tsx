import React, { useState } from 'react';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import Container from "@cloudscape-design/components/container";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Badge from "@cloudscape-design/components/badge";
import Box from "@cloudscape-design/components/box";
import Icon from "@cloudscape-design/components/icon";
import Modal from "@cloudscape-design/components/modal";
import StepFormModal from './usecase/StepFormModal';
import './WorkflowStepsCard.css';
import './StepsTable.css';

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
  capture_variable?: string;
}

interface WorkflowStepsCardProps {
  steps: UsecaseStep[];
  onReorder: (reorderedSteps: UsecaseStep[]) => Promise<void>;
  onUpdateStep: (stepData: any) => Promise<void>;
  onDeleteStep: (stepId: string) => void;
  onAddStep: (stepData: any, position?: number) => Promise<void>;
  usecaseId: string;
}

interface SortableStepCardProps {
  step: UsecaseStep;
  index: number;
  totalSteps: number;
  onEdit: (step: UsecaseStep) => void;
  onDelete: (step: UsecaseStep) => void;
  onAddAbove: () => void;
  onAddBelow: () => void;
  isDeleting: boolean;
}

function SortableStepCard({
  step,
  index,
  totalSteps,
  onEdit,
  onDelete,
  onAddAbove,
  onAddBelow,
  isDeleting,
}: SortableStepCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: step.sk });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const getStepTypeBadge = (stepType?: string) => {
    switch (stepType) {
      case 'secret':
        return <Badge color="red">Secret</Badge>;
      case 'validation':
        return <Badge color="green">Validation</Badge>;
      case 'assertion':
        return <Badge color="green">Assertion</Badge>;
      case 'retrieve_value':
        return <Badge color="blue">Value</Badge>;
      case 'url':
        return <Badge color="severity-medium">Goto</Badge>;
      case 'download':
        return <Badge className="badge-purple">Download</Badge>;
      case 'navigation':
      default:
        return <Badge>Navigation</Badge>;
    }
  };

  const renderStepDetails = () => {
    const details = [];

    if (step.step_type === 'secret' && step.secret_key) {
      details.push(`Secret: ${step.secret_key}`);
    } else if (step.step_type === 'validation') {
      if (step.validation_type === 'bool') {
        const expectedValue = step.validation_value === 'true' ? 'True' : 'False';
        details.push(`Validation: Boolean expects ${expectedValue}`);
      } else if (step.validation_type === 'string') {
        const operator = step.validation_operator === 'exact' ? 'exactly matches' : 'contains';
        details.push(`Validation: Text ${operator} "${step.validation_value}"`);
      } else if (step.validation_type === 'number') {
        const getOperatorText = (op?: string) => {
          switch (op) {
            case 'equals': return 'equals';
            case 'less_then': return 'is less than';
            case 'greater_then': return 'is greater than';
            case 'greater_or_equal_then': return 'is greater than or equal to';
            case 'less_or_equal_then': return 'is less than or equal to';
            default: return 'equals';
          }
        };
        const operatorText = getOperatorText(step.validation_operator);
        details.push(`Validation: Number ${operatorText} ${step.validation_value}`);
      }
    } else if (step.step_type === 'assertion') {
      if (step.validation_type === 'bool') {
        const expectedValue = step.validation_value === 'true' ? 'True' : 'False';
        details.push(`Variable: ${(step as any).assertion_variable}`);
        details.push(`Assertion: Boolean expects ${expectedValue}`);
      } else if (step.validation_type === 'string') {
        const operator = step.validation_operator === 'exact' ? 'exactly matches' : 'contains';
        details.push(`Variable: ${(step as any).assertion_variable}`);
        details.push(`Assertion: Text ${operator} "${step.validation_value}"`);
      } else if (step.validation_type === 'number') {
        const getOperatorText = (op?: string) => {
          switch (op) {
            case 'equals': return 'equals';
            case 'less_then': return 'is less than';
            case 'greater_then': return 'is greater than';
            case 'greater_or_equal_then': return 'is greater than or equal to';
            case 'less_or_equal_then': return 'is less than or equal to';
            default: return 'equals';
          }
        };
        const operatorText = getOperatorText(step.validation_operator);
        details.push(`Variable: ${(step as any).assertion_variable}`);
        details.push(`Assertion: Number ${operatorText} ${step.validation_value}`);
      }
    } else if (step.step_type === 'retrieve_value' && step.capture_variable) {
      details.push(`Captures variable: ${step.capture_variable}`);
    }

    return details;
  };

  const details = renderStepDetails();

  const cardClassName = isDragging 
    ? 'workflow-step-card-dragging' 
    : isDeleting 
    ? 'workflow-step-card workflow-step-card-deleting'
    : 'workflow-step-card';

  return (
    <div ref={setNodeRef} style={style} className={cardClassName}>
      <Container>
        <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
          {/* Drag Handle */}
          <div
            {...attributes}
            {...listeners}
            className="drag-handle"
            style={{
              padding: '8px',
              display: 'flex',
              alignItems: 'center',
              color: '#5f6b7a',
            }}
          >
            <Icon name="drag-indicator" size="medium" />
          </div>

          {/* Step Number */}
          <div className="step-number">
            {step.sort}
          </div>

          {/* Step Content */}
          <div className="step-content">
            <SpaceBetween direction="vertical" size="xs">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {getStepTypeBadge(step.step_type)}
              </div>

              <div className="step-instruction">
                {step.instruction}
              </div>

              {details.length > 0 && (
                <div className="step-details">
                  {details.map((detail, idx) => (
                    <div key={idx}>{detail}</div>
                  ))}
                </div>
              )}
            </SpaceBetween>
          </div>

          {/* Actions */}
          <div className="step-actions">
            <div className="step-actions-group">
              <Button
                iconName="add-plus"
                onClick={onAddAbove}
                variant='inline-link'
              >
                Add step above
              </Button>
              <Button
                iconName="add-plus"
                onClick={onAddBelow}
                variant='inline-link'
              >
                Add step below
              </Button>
            </div>
            <div className="step-actions-divider" />
            <div className="step-actions-group">
              <Button
                variant="icon"
                iconName="edit"
                ariaLabel="Edit step"
                onClick={() => onEdit(step)}
                disabled={isDeleting}
              />
              <Button
                variant="icon"
                iconName="remove"
                ariaLabel="Delete step"
                onClick={() => onDelete(step)}
                loading={isDeleting}
                disabled={isDeleting}
              />
            </div>
          </div>
        </div>
      </Container>
    </div>
  );
}

export default function WorkflowStepsCard({
  steps,
  onReorder,
  onUpdateStep,
  onDeleteStep,
  onAddStep,
  usecaseId,
}: WorkflowStepsCardProps) {
  const [editingStep, setEditingStep] = useState<UsecaseStep | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [addPosition, setAddPosition] = useState<number | undefined>(undefined);
  const [isReordering, setIsReordering] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deletingStep, setDeletingStep] = useState<UsecaseStep | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      const oldIndex = steps.findIndex((step) => step.sk === active.id);
      const newIndex = steps.findIndex((step) => step.sk === over.id);

      const reorderedSteps = arrayMove(steps, oldIndex, newIndex).map((step, index) => ({
        ...step,
        sort: index + 1,
      }));

      setIsReordering(true);
      try {
        await onReorder(reorderedSteps);
      } finally {
        setIsReordering(false);
      }
    }
  };

  const handleEditStep = (step: UsecaseStep) => {
    setEditingStep(step);
    setShowEditModal(true);
  };

  const handleUpdateStep = async (stepData: any) => {
    if (!editingStep) return;

    const updatedStep = {
      ...editingStep,
      ...stepData
    };

    await onUpdateStep(updatedStep);
    setEditingStep(null);
    setShowEditModal(false);
  };

  const handleAddAbove = (step: UsecaseStep) => {
    // Add above means insert at the current step's sort position
    setAddPosition(step.sort);
    setShowAddModal(true);
  };

  const handleAddBelow = (step: UsecaseStep) => {
    // Add below means insert at the next sort position
    setAddPosition(step.sort + 1);
    setShowAddModal(true);
  };

  const handleAddStep = async (stepData: any) => {
    await onAddStep(stepData, addPosition);
    setShowAddModal(false);
    setAddPosition(undefined);
  };

  const handleDeleteClick = (step: UsecaseStep) => {
    setDeletingStep(step);
    setShowDeleteModal(true);
  };

  const handleConfirmDelete = async () => {
    if (!deletingStep) return;
    
    setIsDeleting(true);
    try {
      await onDeleteStep(deletingStep.sk);
      setShowDeleteModal(false);
      setDeletingStep(null);
    } catch (error) {
      console.error('Failed to delete step:', error);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleCancelDelete = () => {
    setShowDeleteModal(false);
    setDeletingStep(null);
  };

  if (steps.length === 0) {
    return (
      <>
        <StepFormModal
          visible={showAddModal}
          onDismiss={() => {
            setShowAddModal(false);
            setAddPosition(undefined);
          }}
          onSubmit={handleAddStep}
          usecaseId={usecaseId}
          title="Add Step"
          existingSteps={steps}
        />
        <Container>
          <Box textAlign="center" padding="xxl">
            <SpaceBetween direction="vertical" size="m">
              <Icon name="status-info" size="big" variant="subtle" />
              <Box variant="h3">No workflow steps yet</Box>
              <Box variant="p" color="text-body-secondary">
                Get started by creating your first workflow step. You can add navigation actions, validations, and more.
              </Box>
              <Button variant="primary" onClick={() => setShowAddModal(true)}>
                Add First Step
              </Button>
            </SpaceBetween>
          </Box>
        </Container>
      </>
    );
  }

  return (
    <>
      <StepFormModal
        visible={showEditModal}
        onDismiss={() => {
          setShowEditModal(false);
          setEditingStep(null);
        }}
        onSubmit={handleUpdateStep}
        step={editingStep}
        usecaseId={usecaseId}
        title="Edit Step"
        existingSteps={steps}
      />

      <StepFormModal
        visible={showAddModal}
        onDismiss={() => {
          setShowAddModal(false);
          setAddPosition(undefined);
        }}
        onSubmit={handleAddStep}
        usecaseId={usecaseId}
        title={addPosition !== undefined ? `Add Step at Position ${addPosition}` : 'Add Step'}
        existingSteps={steps}
      />

      <Modal
        onDismiss={handleCancelDelete}
        visible={showDeleteModal}
        closeAriaLabel="Close modal"
        size="small"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={handleCancelDelete} disabled={isDeleting}>
                Cancel
              </Button>
              <Button 
                variant="primary" 
                onClick={handleConfirmDelete}
                loading={isDeleting}
                disabled={isDeleting}
              >
                Delete
              </Button>
            </SpaceBetween>
          </Box>
        }
        header="Delete step?"
      >
        {deletingStep && (
          <Box variant="span">
            Are you sure you want to delete <strong>Step {deletingStep.sort}</strong>?
          </Box>
        )}
      </Modal>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={steps.map((step) => step.sk)}
          strategy={verticalListSortingStrategy}
        >
          <SpaceBetween direction="vertical" size="s">
            {steps.map((step, index) => (
              <SortableStepCard
                key={step.sk}
                step={step}
                index={index}
                totalSteps={steps.length}
                onEdit={handleEditStep}
                onDelete={handleDeleteClick}
                onAddAbove={() => handleAddAbove(step)}
                onAddBelow={() => handleAddBelow(step)}
                isDeleting={isDeleting && deletingStep?.sk === step.sk}
              />
            ))}
          </SpaceBetween>
        </SortableContext>
      </DndContext>

      {isReordering && (
        <Box margin={{ top: 's' }} textAlign="center">
          <Box variant="p" color="text-status-info">
            Reordering steps...
          </Box>
        </Box>
      )}
    </>
  );
}
