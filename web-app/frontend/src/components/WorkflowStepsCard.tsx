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
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import Container from "@cloudscape-design/components/container";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Box from "@cloudscape-design/components/box";
import Icon from "@cloudscape-design/components/icon";
import Badge from "@cloudscape-design/components/badge";
import Modal from "@cloudscape-design/components/modal";
import StepFormModal from './usecase/StepFormModal';
import {
  blockEndPosition,
  childrenOf,
  groupStepsByParent,
  orderStepsByTree,
  reorderStepTree,
  type StepBlock,
} from './usecase/stepTree';
import './WorkflowStepsCard.css';
import StepTypeBadge from './common/StepTypeBadge';
import { hasExpectation, stepDetailLines } from './usecase/stepDetails';
import type { ApplicationDatasetSummary } from '../utils/api';
import { formatTimeAgo } from '../utils/time';

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
  template_id?: string;
  template_step_id?: string;
  template_version?: number;
  // Native trajectory replay (CLI runner): set when a navigation step has a
  // recorded trajectory it will replay instead of calling the model.
  trajectory_s3_key?: string | null;
  trajectory_last_updated?: string | null;
  browser_action?: string;
  browser_args?: string;
  transform_operation?: string;
  transform_args?: string;
  network_url_pattern?: string | null;
  network_method?: string | null;
  network_request_body?: string | null;
  network_body_match_type?: string | null;
  network_mock_response?: string | null;
  network_mock_passthrough?: boolean;
  network_timeout?: number | null;
  network_response_body?: string | null;
  network_response_body_match_type?: string | null;
  network_response_status?: number | null;
  id?: string;
  parent_step_id?: string | null;
  repeat_columns?: string[];
  repeat_rows?: string[][];
  dataset_id?: string | null;
}

interface WorkflowStepsCardProps {
  steps: UsecaseStep[];
  onReorder: (reorderedSteps: UsecaseStep[]) => Promise<void>;
  onUpdateStep: (stepData: any) => Promise<void>;
  onDeleteStep: (stepId: string) => void;
  onAddStep: (stepData: any, position?: number) => Promise<void>;
  onUpdateFromTemplate?: (stepId: string) => Promise<void>;
  usecaseId: string;
  /** Owning application; enables the application-dataset source in the step modal. */
  applicationId?: string;
  /** The application's datasets: names dataset_id repeats and feeds the step modal. */
  datasets?: ApplicationDatasetSummary[];
}

/**
 * "Cached" = the step replays a recorded trajectory instead of calling the
 * model. Only navigation steps record trajectories (the CLI's
 * StepExecutor._execute_navigation is the sole TrajectoryManager.save_trajectory
 * caller); a step without step_type is a navigation step.
 */
function hasReplayableTrajectory(step: UsecaseStep): boolean {
  const isNavigation = !step.step_type || step.step_type === 'navigation';
  return isNavigation && Boolean(step.trajectory_s3_key);
}

interface SortableStepCardProps {
  step: UsecaseStep;
  index: number;
  totalSteps: number;
  onEdit: (step: UsecaseStep) => void;
  onDelete: (step: UsecaseStep) => void;
  onAddAbove: () => void;
  onAddBelow: () => void;
  onAddInside?: () => void;
  isDeleting: boolean;
  isChild?: boolean;
  orphan?: boolean;
  childCount?: number;
  datasets: ApplicationDatasetSummary[];
}

function SortableStepCard({
  step,
  index,
  totalSteps,
  onEdit,
  onDelete,
  onAddAbove,
  onAddBelow,
  onAddInside,
  isDeleting,
  isChild = false,
  orphan = false,
  childCount = 0,
  datasets,
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

  // Validate step for missing required information
  const validateStep = (): string[] => {
    const issues: string[] = [];
    
    if (step.step_type === 'secret' && !step.secret_key) {
      issues.push('Secret key is not configured');
    }
    
    if (step.step_type === 'validation') {
      if (!step.validation_type) {
        issues.push('Validation type is not set');
      }
      if (!step.validation_value) {
        issues.push('Validation value is not set');
      }
    }
    
    if (step.step_type === 'assertion') {
      if (!step.assertion_variable) {
        issues.push('Assertion variable is not set');
      }
      if (!step.validation_type) {
        issues.push('Validation type is not set');
      }
      if (!step.validation_value) {
        issues.push('Validation value is not set');
      }
    }
    
    if (step.step_type === 'retrieve_value' && !step.capture_variable) {
      issues.push('Capture variable is not set');
    }
    
    if (!step.instruction || step.instruction.trim() === '') {
      issues.push(step.step_type === 'repeat' ? 'Label is empty' : 'Instruction is empty');
    }

    if (step.step_type === 'repeat' && !step.dataset_id && (!step.repeat_columns?.length || !step.repeat_rows?.length)) {
      issues.push('Dataset is empty');
    }

    if (orphan) {
      issues.push('Parent repeat step not found');
    }
    
    return issues;
  };

  const validationIssues = validateStep();
  const hasIssues = validationIssues.length > 0;

  // The card shows the instruction separately; an assertion's variable leads its details.
  const details = [
    ...(step.step_type === 'assertion' && hasExpectation(step) ? [`Variable: ${step.assertion_variable}`] : []),
    ...stepDetailLines(step, datasets),
  ];
  const isCached = hasReplayableTrajectory(step);
  // Age of the recorded trajectory the step will replay
  if (isCached && step.trajectory_last_updated) {
    details.push(`Cached ${formatTimeAgo(step.trajectory_last_updated)}`);
  }

  const cardClassName = [
    isDragging ? 'workflow-step-card-dragging' : 'workflow-step-card',
    !isDragging && isDeleting ? 'workflow-step-card-deleting' : '',
    isChild ? 'workflow-step-card-child' : '',
  ].filter(Boolean).join(' ');

  return (
    <div ref={setNodeRef} style={style} className={cardClassName} data-testid={isChild ? 'child-step-card' : 'step-card'}>
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

          {isChild && (
            <div className="step-child-marker" aria-hidden="true">↳</div>
          )}

          {/* Step Content */}
          <div className="step-content">
            <SpaceBetween direction="vertical" size="xs">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <StepTypeBadge stepType={step.step_type} />
                {isCached && (
                  <Badge color="green">
                    <Icon name="check" /> Cached
                  </Badge>
                )}
                {hasIssues && (
                  <div title={validationIssues.join(', ')} style={{ display: 'flex', alignItems: 'center' }}>
                    <Box color="text-status-warning">
                      <Icon name="status-warning" size="medium" />
                    </Box>
                  </div>
                )}
              </div>

              <div className="step-instruction">
                {step.instruction || <Box color="text-status-warning">(No instruction provided)</Box>}
              </div>

              {details.length > 0 && (
                <div className="step-details">
                  {details.map((detail, idx) => (
                    <div key={idx}>{detail}</div>
                  ))}
                </div>
              )}

              {hasIssues && (
                <div className="step-details" style={{ color: '#d91515' }}>
                  {validationIssues.map((issue, idx) => (
                    <div key={idx}>⚠ {issue}</div>
                  ))}
                </div>
              )}

              {step.template_id && (
                <div style={{ 
                  marginTop: '8px',
                  fontSize: '0.85em',
                  color: '#5f6b7a'
                }}>
                  From template: 
                  <a 
                    href={`/templates/${step.template_id}`}
                    style={{ marginLeft: '4px', color: '#0972d3' }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    View Template
                  </a>
                  {step.template_version && ` (v${step.template_version})`}
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
              {step.step_type === 'repeat' && onAddInside && (
                <Button
                  iconName="add-plus"
                  onClick={onAddInside}
                  variant='inline-link'
                >
                  Add step inside
                </Button>
              )}
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
  onUpdateFromTemplate,
  usecaseId,
  applicationId,
  datasets = [],
}: WorkflowStepsCardProps) {
  const [editingStep, setEditingStep] = useState<UsecaseStep | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [addPosition, setAddPosition] = useState<number | undefined>(undefined);
  const [addParentId, setAddParentId] = useState<string | undefined>(undefined);
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
      // Block-aware: a repeat moves with its children, a child stays in
      // its block. A rejected move returns null and the card snaps back.
      const reorderedSteps = reorderStepTree(steps, String(active.id), String(over.id));
      if (!reorderedSteps) return;

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
    // Add above means insert at the current step's sort position. A child
    // stays inside its repeat.
    setAddPosition(step.sort);
    setAddParentId(step.parent_step_id || undefined);
    setShowAddModal(true);
  };

  const handleAddBelow = (step: UsecaseStep) => {
    // Add below means insert at the next sort position; below a repeat
    // means after its whole block (as a top-level step).
    setAddPosition(step.step_type === 'repeat' ? blockEndPosition(steps, step.sk) : step.sort + 1);
    setAddParentId(step.parent_step_id || undefined);
    setShowAddModal(true);
  };

  const handleAddInside = (repeat: UsecaseStep) => {
    // New children go to the end of the block.
    setAddPosition(blockEndPosition(steps, repeat.sk));
    setAddParentId(repeat.id || repeat.sk.replace('STEP#', ''));
    setShowAddModal(true);
  };

  const handleAddStep = async (stepData: any) => {
    await onAddStep(stepData, addPosition);
    setShowAddModal(false);
    setAddPosition(undefined);
    setAddParentId(undefined);
  };

  const deletingChildren = deletingStep?.step_type === 'repeat' ? childrenOf(steps, deletingStep.sk) : [];

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

  const handleUpdateFromTemplateInModal = async () => {
    if (!onUpdateFromTemplate || !editingStep) return;
    
    const stepId = editingStep.sk.replace('STEP#', '');
    await onUpdateFromTemplate(stepId);
  };

  if (steps.length === 0) {
    return (
      <>
        <StepFormModal
          visible={showAddModal}
          onDismiss={() => {
            setShowAddModal(false);
            setAddPosition(undefined);
            setAddParentId(undefined);
          }}
          onSubmit={handleAddStep}
          usecaseId={usecaseId}
          title="Add Step"
          existingSteps={steps}
          applicationId={applicationId}
          datasets={datasets}
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
        onUpdateFromTemplate={editingStep?.template_step_id && onUpdateFromTemplate ? 
          handleUpdateFromTemplateInModal : 
          undefined
        }
        step={editingStep}
        usecaseId={usecaseId}
        title="Edit Step"
        existingSteps={steps}
        applicationId={applicationId}
        datasets={datasets}
      />

      <StepFormModal
        visible={showAddModal}
        onDismiss={() => {
          setShowAddModal(false);
          setAddPosition(undefined);
          setAddParentId(undefined);
        }}
        onSubmit={handleAddStep}
        usecaseId={usecaseId}
        title={addParentId
          ? 'Add Step Inside Repeat'
          : addPosition !== undefined ? `Add Step at Position ${addPosition}` : 'Add Step'}
        existingSteps={steps}
        parentStepId={addParentId}
        applicationId={applicationId}
        datasets={datasets}
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
            {deletingStep.step_type === 'repeat' && (
              <>
                {' '}This repeat step contains <strong>{deletingChildren.length}</strong>{' '}
                {deletingChildren.length === 1 ? 'step' : 'steps'}; deleting it removes
                {deletingChildren.length === 1 ? ' it' : ' them'} too.
              </>
            )}
          </Box>
        )}
      </Modal>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={orderStepsByTree(steps).map((step) => step.sk)}
          strategy={verticalListSortingStrategy}
        >
          <SpaceBetween direction="vertical" size="s">
            {groupStepsByParent(steps).map((block: StepBlock<UsecaseStep>, index) => {
              const isRepeat = block.head.step_type === 'repeat';
              return (
                <div key={block.head.sk} className={isRepeat ? 'workflow-step-block' : undefined}>
                  <SortableStepCard
                    step={block.head}
                    index={index}
                    totalSteps={steps.length}
                    onEdit={handleEditStep}
                    onDelete={handleDeleteClick}
                    onAddAbove={() => handleAddAbove(block.head)}
                    onAddBelow={() => handleAddBelow(block.head)}
                    onAddInside={isRepeat ? () => handleAddInside(block.head) : undefined}
                    isDeleting={isDeleting && deletingStep?.sk === block.head.sk}
                    orphan={block.orphan}
                    childCount={block.children.length}
                    datasets={datasets}
                  />
                  {isRepeat && (
                    <div className="workflow-step-children" data-testid="repeat-children">
                      {block.children.length === 0 ? (
                        <Box color="text-body-secondary" fontSize="body-s" padding={{ vertical: 'xs' }}>
                          No steps inside yet — use "Add step inside" to add the first one.
                        </Box>
                      ) : (
                        <SpaceBetween direction="vertical" size="xs">
                          {block.children.map((child) => (
                            <SortableStepCard
                              key={child.sk}
                              step={child}
                              index={index}
                              totalSteps={steps.length}
                              onEdit={handleEditStep}
                              onDelete={handleDeleteClick}
                              onAddAbove={() => handleAddAbove(child)}
                              onAddBelow={() => handleAddBelow(child)}
                              isDeleting={isDeleting && deletingStep?.sk === child.sk}
                              isChild
                              datasets={datasets}
                            />
                          ))}
                        </SpaceBetween>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
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
