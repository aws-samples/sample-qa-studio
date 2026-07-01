import React, { useState } from 'react';
import Table from "@cloudscape-design/components/table";
import Link from "@cloudscape-design/components/link";
import Button from "@cloudscape-design/components/button";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Badge from "@cloudscape-design/components/badge";
import Icon from "@cloudscape-design/components/icon";
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
  cached_steps?: string | null;
  cache_last_updated?: string | null;
  browser_action?: string;
  browser_args?: string;
  transform_operation?: string;
  transform_args?: string;
  network_url_pattern?: string | null;
  network_method?: string | null;
  network_request_body?: string | null;
  network_body_match_type?: string | null;
  network_mock_response?: string | null;
  network_mock_passthrough?: boolean | null;
  network_timeout?: number | null;
  network_response_body?: string | null;
  network_response_body_match_type?: string | null;
  network_response_status?: number | null;
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

  const getRelativeTime = (timestamp: string): string => {
    const now = new Date();
    const past = new Date(timestamp);
    const diffMs = now.getTime() - past.getTime();
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffDays > 0) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
    if (diffHours > 0) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    if (diffMins > 0) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
    return 'just now';
  };

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

  const getStepTypeBadge = (item: UsecaseStep) => {
    const stepType = item.step_type;
    const hasCachedSteps = item.cached_steps && item.cached_steps !== 'null';
    const isNavigation = !stepType || stepType === 'navigation';
    
    let typeBadge;
    switch (stepType) {
      case 'secret':
        typeBadge = <Badge color="severity-high" className="step">Secret</Badge>;
        break;
      case 'validation':
        typeBadge = <Badge color="green" className="step">Validation</Badge>;
        break;
      case 'assertion':
        typeBadge = <Badge color="green" className="step">Assertion</Badge>;
        break;
      case 'retrieve_value':
        typeBadge = <Badge color="blue" className="step">Value</Badge>;
        break;
      case 'url':
        typeBadge = <Badge color="severity-medium" className="step">Goto (deprecated)</Badge>;
        break;
      case 'browser':
        typeBadge = <Badge color="severity-medium" className="step">Browser</Badge>;
        break;
      case 'transform':
        typeBadge = <Badge color="blue" className="step">Transform</Badge>;
        break;
      case 'download':
        typeBadge = <Badge className="step badge-purple">Download</Badge>;
        break;
      case 'network_assertion':
        typeBadge = <Badge color="blue" className="step">Network</Badge>;
        break;
      case 'navigation':
      default:
        typeBadge = <Badge className="step">Navigation</Badge>;
        break;
    }

    return (
      <SpaceBetween direction="vertical" size="xxs">
        {typeBadge}
        {isNavigation && hasCachedSteps && (
          <Badge color="green">
            <Icon name="check" /> Cached
          </Badge>
        )}
      </SpaceBetween>
    );
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
    } else if (item.step_type === 'network_assertion' && item.network_url_pattern) {
      const parts = [`Network: ${item.network_method || 'any'} ${item.network_url_pattern}`];
      if (item.network_request_body) {
        parts.push(`req body (${item.network_body_match_type || 'exact'})`);
      }
      if (item.network_mock_response) {
        parts.push(item.network_mock_passthrough ? 'passthrough mock' : 'static mock');
      }
      if (item.network_response_status != null) {
        parts.push(`resp ${item.network_response_status}`);
      }
      if (item.network_response_body) {
        parts.push(`resp body (${item.network_response_body_match_type || 'subset'})`);
      }
      details.push(parts.join(' · '));
    }

    // Add cache age for navigation steps with cache
    const isNavigation = !item.step_type || item.step_type === 'navigation';
    const hasCachedSteps = item.cached_steps && item.cached_steps !== 'null';
    if (isNavigation && hasCachedSteps && item.cache_last_updated) {
      details.push(`Cached ${getRelativeTime(item.cache_last_updated)}`);
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
          cell: item => getStepTypeBadge(item),
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