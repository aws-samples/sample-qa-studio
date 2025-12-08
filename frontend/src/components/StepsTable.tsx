import React, { useState } from 'react';
import Table from "@cloudscape-design/components/table";
import Link from "@cloudscape-design/components/link";
import Button from "@cloudscape-design/components/button";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Badge from "@cloudscape-design/components/badge";
import { api } from '../utils/api';
import StepFormModal from './usecase/StepFormModal';
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
  template_id?: string;
  template_step_id?: string;
  template_version?: number;
}

interface StepsTableProps {
  steps: UsecaseStep[];
  onStepsReordered: () => void;
  onUpdateStep: (stepData: any) => Promise<void>;
  onDeleteStep: (stepId: string) => void;
  usecaseId: string;
}

export default function StepsTable({ 
  steps, 
  onStepsReordered, 
  onUpdateStep, 
  onDeleteStep, 
  usecaseId 
}: StepsTableProps) {
  const [movingSteps, setMovingSteps] = useState<Set<string>>(new Set());
  const [editingStep, setEditingStep] = useState<UsecaseStep | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);

  const moveStep = async (stepId: string, direction: 'up' | 'down') => {
    const currentIndex = steps.findIndex(step => step.sk === stepId);
    if (currentIndex === -1) return;

    const targetIndex = direction === 'up' ? currentIndex - 1 : currentIndex + 1;
    if (targetIndex < 0 || targetIndex >= steps.length) return;

    const currentStep = steps[currentIndex];
    const targetStep = steps[targetIndex];

    setMovingSteps(prev => new Set([...prev, currentStep.sk, targetStep.sk]));

    try {
      // Swap the sort values of the two steps
      const stepOrders = [
        {
          step_id: currentStep.sk,
          sort: targetStep.sort
        },
        {
          step_id: targetStep.sk,
          sort: currentStep.sort
        }
      ];

      await api.patch(`usecase/${usecaseId}/steps/reorder`, {
        step_orders: stepOrders
      });

      // Refresh the data
      onStepsReordered();
    } catch (error) {
      console.error('Failed to reorder steps:', error);
    } finally {
      setMovingSteps(prev => {
        const newSet = new Set(prev);
        newSet.delete(currentStep.sk);
        newSet.delete(targetStep.sk);
        return newSet;
      });
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

  const getStepTypeBadge = (stepType?: string) => {
    switch (stepType) {
      case 'secret':
        return <Badge color="severity-high" className="step">Secret</Badge>;
      case 'validation':
        return <Badge color="green" className="step">Validation</Badge>;
      case 'assertion':
          return <Badge color="green" className="step">Assertion</Badge>;
      case 'retrieve_value':
        return <Badge color="blue" className="step">Value</Badge>;
      case 'url':
        return <Badge color="severity-medium" className="step">Goto</Badge>;
      case 'download':
        return <Badge className="step badge-purple">Download</Badge>;
      case 'navigation':
      default:
        return <Badge className="step">Navigation</Badge>;
    }
  };

  const renderStepDetails = (item: UsecaseStep) => {
    const details = [item.instruction];
    
    if (item.step_type === 'secret' && item.secret_key) {
      details.push(`Secret: ${item.secret_key}`);
    } else if (item.step_type === 'validation') {
      if (item.validation_type === 'bool') {
        const expectedValue = item.validation_value === 'true' ? 'True' : 'False';
        details.push(`Validation: Boolean expects ${expectedValue}`);
      } else if (item.validation_type === 'string') {
        const getStringOperatorText = (op?: string) => {
          switch (op) {
            case 'exact': return 'exactly matches';
            case 'exact_case_insensitive': return 'exactly matches (case insensitive)';
            case 'not_equal': return 'does not equal';
            case 'contains': return 'contains';
            case 'contains_case_insensitive': return 'contains (case insensitive)';
            default: return 'exactly matches';
          }
        };
        const operator = getStringOperatorText(item.validation_operator);
        details.push(`Validation: Text ${operator} "${item.validation_value}"`);
      } else if (item.validation_type === 'number') {
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
        const operatorText = getOperatorText(item.validation_operator);
        details.push(`Validation: Number ${operatorText} ${item.validation_value}`);
      }
    } else if (item.step_type === 'assertion') {
      details[0] = `Assert variable: ${(item as any).assertion_variable}`;
      if (item.validation_type === 'bool') {
        const expectedValue = item.validation_value === 'true' ? 'True' : 'False';
        details.push(`Assertion: Boolean expects ${expectedValue}`);
      } else if (item.validation_type === 'string') {
        const getStringOperatorText = (op?: string) => {
          switch (op) {
            case 'exact': return 'exactly matches';
            case 'exact_case_insensitive': return 'exactly matches (case insensitive)';
            case 'not_equal': return 'does not equal';
            case 'contains': return 'contains';
            case 'contains_case_insensitive': return 'contains (case insensitive)';
            default: return 'exactly matches';
          }
        };
        const operator = getStringOperatorText(item.validation_operator);
        details.push(`Assertion: Text ${operator} "${item.validation_value}"`);
      } else if (item.validation_type === 'number') {
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
        const operatorText = getOperatorText(item.validation_operator);
        details.push(`Assertion: Number ${operatorText} ${item.validation_value}`);
      }
    } else if (item.step_type === 'retrieve_value' && item.capture_variable) {
      details.push(`Captures variable: ${item.capture_variable}`);
    }
    
    return (
      <div>
        {details.map((detail, index) => (
          <div 
            key={index}
            style={{ 
              fontSize: index === 0 ? '14px' : '12px',
              color: index === 0 ? 'inherit' : '#5f6b7a',
              marginTop: index === 0 ? '0' : '4px',
              fontStyle: index === 0 ? 'normal' : 'italic'
            }}
          >
            {detail}
          </div>
        ))}
      </div>
    );
  };

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
    <Table
      columnDefinitions={[
        { 
          id: 'sort', 
          header: 'Step', 
          cell: item => item.sort,
          maxWidth: 60,
        },
        { 
          id: 'type', 
          header: 'Type', 
          cell: item => getStepTypeBadge(item.step_type),
          maxWidth: 120,
          minWidth: 120,
        },
        { 
          id: 'instruction', 
          header: 'Details', 
          cell: item => renderStepDetails(item)
        },
        { 
          id: 'reorder', 
          header: 'Reorder', 
          cell: (item: any) => {
            const currentIndex = steps.findIndex(step => step.sk === item.sk);
            const isFirst = currentIndex === 0;
            const isLast = currentIndex === steps.length - 1;
            const isMoving = movingSteps.has(item.sk);

            return (
              <SpaceBetween direction="horizontal" size="xs">
                <Button
                  variant="icon"
                  iconName="angle-up"
                  disabled={isFirst || isMoving}
                  loading={isMoving}
                  onClick={() => moveStep(item.sk, 'up')}
                  ariaLabel="Move step up"
                />
                <Button
                  variant="icon"
                  iconName="angle-down"
                  disabled={isLast || isMoving}
                  loading={isMoving}
                  onClick={() => moveStep(item.sk, 'down')}
                  ariaLabel="Move step down"
                />
              </SpaceBetween>
            );
          },
          maxWidth: 100,
        },
        { 
          id: 'actions', 
          header: 'Actions', 
          cell: item => (
            <SpaceBetween direction="horizontal" size="xs">
              <Link onClick={() => handleEditStep(item)}>Edit</Link>
              <Link onClick={() => onDeleteStep(item.sk)}>Delete</Link>
            </SpaceBetween>
          ),
          maxWidth: 120,
        }
      ]}
      items={[...steps].sort((a, b) => a.sort - b.sort)}
      empty="No workflow steps defined. Click 'Add Step' to create your first step."
    />
    </>
  );
}