import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Box from "@cloudscape-design/components/box";
import ColumnLayout from "@cloudscape-design/components/column-layout";
import Badge from "@cloudscape-design/components/badge";
import Spinner from "@cloudscape-design/components/spinner";
import Modal from "@cloudscape-design/components/modal";
import FormField from "@cloudscape-design/components/form-field";
import Input from "@cloudscape-design/components/input";
import Table from "@cloudscape-design/components/table";
import CopyToClipboard from "@cloudscape-design/components/copy-to-clipboard";
import { api } from '../../utils/api';
import StepFormModal from '../usecase/StepFormModal';
import WorkflowStepsCard from '../WorkflowStepsCard';

interface Template {
  id: string;
  name: string;
  description: string;
  category: string;
  tags?: string[];
  created_by: string;
  created_at: string;
  updated_at: string;
  version: number;
}

interface TemplateStep {
  id: string;
  sort: number;
  instruction: string;
  step_type: string;
  secret_key?: string;
  capture_variable?: string;
  validation_type?: string;
  validation_operator?: string;
  validation_value?: string;
  assertion_variable?: string;
  value_type?: string;
}

interface Variable {
  key: string;
  value: string;
}

export default function TemplateDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [template, setTemplate] = useState<Template | null>(null);
  const [steps, setSteps] = useState<TemplateStep[]>([]);
  const [variables, setVariables] = useState<Variable[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Step modal state
  const [showStepModal, setShowStepModal] = useState(false);
  const [editingStep, setEditingStep] = useState<TemplateStep | null>(null);
  
  // Variable modal state
  const [showVariableModal, setShowVariableModal] = useState(false);
  const [variableKey, setVariableKey] = useState('');
  const [variableValue, setVariableValue] = useState('');
  const [savingVariables, setSavingVariables] = useState(false);

  const fetchData = async () => {
    if (!id) return;

    try {
      const [templateData, stepsData, variablesData] = await Promise.all([
        api.get(`templates/${id}`),
        api.get(`templates/${id}/steps`),
        api.get(`templates/${id}/variables`)
      ]);
      
      setTemplate(templateData);
      setSteps(stepsData.steps || []);
      setVariables(variablesData.variables || []);
    } catch (error) {
      console.error('Failed to fetch template:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [id]);

  const handleDelete = async () => {
    if (!id || !window.confirm('Are you sure you want to delete this template?')) return;

    try {
      await api.delete(`templates/${id}`);
      navigate('/templates');
    } catch (error) {
      console.error('Failed to delete template:', error);
    }
  };

  const handleAddStep = () => {
    setEditingStep(null);
    setShowStepModal(true);
  };

  const handleCreateStep = async (stepData: any) => {
    if (!id) return;

    try {
      // ALWAYS fetch fresh data to get accurate step count
      const freshData = await api.get(`templates/${id}/steps`);
      const currentSteps = freshData.steps || [];
      
      // Find the highest sort value from fresh data and add 1
      const maxSort = currentSteps.length > 0 ? Math.max(...currentSteps.map((s: any) => s.sort)) : 0;
      const newSort = maxSort + 1;
      
      console.log(`Creating new step with sort ${newSort} (current max: ${maxSort}, count: ${currentSteps.length})`);
      
      const fullStepData = {
        sort: newSort,
        ...stepData
      };

      await api.post(`templates/${id}/steps`, fullStepData);
      
      // Fetch data to update UI
      await fetchData();
    } catch (error) {
      console.error('Failed to create step:', error);
      throw error;
    }
  };

  const handleUpdateStep = async (stepData: any) => {
    if (!id) return;

    try {
      // stepData comes from WorkflowStepsCard and includes the step id
      const stepId = stepData.id || stepData.sk?.replace('STEP#', '');
      if (!stepId) {
        console.error('No step ID found in stepData:', stepData);
        return;
      }

      // Extract only the fields that should be updated
      const updateData = {
        sort: stepData.sort,
        instruction: stepData.instruction,
        step_type: stepData.step_type,
        secret_key: stepData.secret_key || '',
        capture_variable: stepData.capture_variable || '',
        validation_type: stepData.validation_type || '',
        validation_operator: stepData.validation_operator || '',
        validation_value: stepData.validation_value || '',
        assertion_variable: stepData.assertion_variable || '',
        value_type: stepData.value_type || ''
      };
      
      console.log(`Updating template step ${stepId} with data:`, updateData);
      await api.patch(`templates/${id}/steps/${stepId}`, updateData);
      await fetchData();
    } catch (error) {
      console.error('Failed to update step:', error);
      throw error;
    }
  };

  const handleDeleteStep = async (stepId: string) => {
    if (!id || !window.confirm('Are you sure you want to delete this step?')) return;

    try {
      // Remove STEP# prefix if present
      const cleanStepId = stepId.replace('STEP#', '');
      await api.delete(`templates/${id}/steps/${cleanStepId}`);
      await fetchData();
    } catch (error) {
      console.error('Failed to delete step:', error);
    }
  };



  const handleReorderSteps = async (reorderedSteps: any[]) => {
    if (!id) return;

    try {
      // reorderedSteps already have the correct sort values from WorkflowStepsCard
      const stepOrders = reorderedSteps.map((step) => ({
        step_id: step.id || step.sk?.replace('STEP#', ''),
        sort: step.sort
      }));

      await api.patch(`templates/${id}/steps/reorder`, {
        step_orders: stepOrders
      });

      await fetchData();
    } catch (error) {
      console.error('Failed to reorder steps:', error);
      throw error;
    }
  };

  const handleAddVariable = () => {
    setVariableKey('');
    setVariableValue('');
    setShowVariableModal(true);
  };

  const handleSaveVariable = () => {
    if (!variableKey.trim()) return;

    const newVariables = [...variables, { key: variableKey.trim(), value: variableValue.trim() }];
    setVariables(newVariables);
    setShowVariableModal(false);
  };

  const handleSaveVariables = async () => {
    if (!id) return;

    console.log('Saving variables:', variables);
    setSavingVariables(true);
    try {
      await api.post(`templates/${id}/variables`, { variables });
      console.log('Variables saved successfully');
      fetchData();
    } catch (error) {
      console.error('Failed to save variables:', error);
    } finally {
      setSavingVariables(false);
    }
  };

  const handleDeleteVariable = (index: number) => {
    setVariables(variables.filter((_, i) => i !== index));
  };

  if (loading) {
    return (
      <Box textAlign="center" padding="xxl">
        <Spinner size="large" />
      </Box>
    );
  }

  if (!template) {
    return (
      <Box textAlign="center" padding="xxl">
        <SpaceBetween size="m">
          <div>Template not found</div>
          <Button onClick={() => navigate('/templates')}>Back to Templates</Button>
        </SpaceBetween>
      </Box>
    );
  }

  return (
    <SpaceBetween direction="vertical" size="l">
      <Header
        variant="h1"
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            <Button onClick={() => navigate('/templates')}>
              Back to Templates
            </Button>
            <Button onClick={handleDelete}>
              Delete Template
            </Button>
          </SpaceBetween>
        }
      >
        {template.name}
      </Header>

      <Container>
        <ColumnLayout columns={2} variant="text-grid">
          <div>
            <Box variant="awsui-key-label">Template ID</Box>
            <CopyToClipboard
              copyButtonAriaLabel="Copy template ID"
              copyErrorText="Failed to copy"
              copySuccessText="Copied"
              textToCopy={template.id}
              variant="inline"
            />
          </div>
          <div>
            <Box variant="awsui-key-label">Description</Box>
            <div>{template.description || '-'}</div>
          </div>
          <div>
            <Box variant="awsui-key-label">Created By</Box>
            <div>{template.created_by}</div>
          </div>
          <div>
            <Box variant="awsui-key-label">Tags</Box>
            <div>
              {template.tags && template.tags.length > 0 ? (
                <SpaceBetween direction="horizontal" size="xs">
                  {template.tags.map((tag: string) => (
                    <Badge key={tag}>{tag}</Badge>
                  ))}
                </SpaceBetween>
              ) : '-'}
            </div>
          </div>
          <div>
            <Box variant="awsui-key-label">Version</Box>
            <div>v{template.version}</div>
          </div>
          <div>
            <Box variant="awsui-key-label">Last Updated</Box>
            <div>{new Date(template.updated_at).toLocaleString()}</div>
          </div>
        </ColumnLayout>
      </Container>

      <Container
        header={
          <Header
            variant="h2"
            description="Steps in this template"
            actions={
              <Button onClick={handleAddStep} iconName="add-plus">
                Add Step
              </Button>
            }
          >
            Template Steps ({steps.length})
          </Header>
        }
      >
        {steps.length > 0 ? (
          <WorkflowStepsCard
            steps={steps.map(step => ({
              ...step,
              pk: `TEMPLATE#${id}`,
              sk: `STEP#${step.id}`,
              usecaseId: id || ''
            }))}
            onReorder={handleReorderSteps}
            onUpdateStep={handleUpdateStep}
            onDeleteStep={(stepId) => handleDeleteStep(stepId.replace('STEP#', ''))}
            onAddStep={handleCreateStep}
            usecaseId={id || ''}
          />
        ) : (
          <Box textAlign="center" padding="l">
            <SpaceBetween size="m">
              <div>No steps defined yet</div>
              <Button onClick={handleAddStep}>Add First Step</Button>
            </SpaceBetween>
          </Box>
        )}
      </Container>

      <Container
        header={
          <Header
            variant="h2"
            description="Variables used in this template"
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                <Button onClick={handleAddVariable} iconName="add-plus">
                  Add Variable
                </Button>
                <Button
                  variant="primary"
                  onClick={handleSaveVariables}
                  loading={savingVariables}
                  disabled={savingVariables}
                >
                  Save Variables
                </Button>
              </SpaceBetween>
            }
          >
            Template Variables ({variables.length})
          </Header>
        }
      >
        {variables.length > 0 ? (
          <Table
            columnDefinitions={[
              {
                id: 'key',
                header: 'Key',
                cell: item => item.key
              },
              {
                id: 'value',
                header: 'Value',
                cell: item => item.value || '-'
              },
              {
                id: 'actions',
                header: 'Actions',
                cell: (item: Variable) => (
                  <Button
                    variant="icon"
                    iconName="remove"
                    onClick={() => handleDeleteVariable(variables.indexOf(item))}
                  />
                ),
                width: 100
              }
            ]}
            items={variables}
            empty="No variables defined yet"
          />
        ) : (
          <Box textAlign="center" padding="l">
            <SpaceBetween size="m">
              <div>No variables defined yet</div>
              <Button onClick={handleAddVariable}>Add First Variable</Button>
            </SpaceBetween>
          </Box>
        )}
      </Container>

      {/* Add/Edit Step Modal - Reusing the same modal from use cases */}
      <StepFormModal
        visible={showStepModal}
        onDismiss={() => {
          setShowStepModal(false);
          setEditingStep(null);
        }}
        onSubmit={editingStep ? handleUpdateStep : handleCreateStep}
        step={editingStep}
        usecaseId={id || ''}
        title={editingStep ? 'Edit Template Step' : 'Add Template Step'}
        existingSteps={steps}
      />

      {/* Add Variable Modal */}
      <Modal
        visible={showVariableModal}
        onDismiss={() => setShowVariableModal(false)}
        header="Add Variable"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setShowVariableModal(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleSaveVariable}
                disabled={!variableKey.trim()}
              >
                Add Variable
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <SpaceBetween direction="vertical" size="l">
          <FormField label="Key" description="Variable name">
            <Input
              value={variableKey}
              onChange={({ detail }) => setVariableKey(detail.value)}
              placeholder="e.g., base_url"
            />
          </FormField>

          <FormField label="Value" description="Default value (optional)">
            <Input
              value={variableValue}
              onChange={({ detail }) => setVariableValue(detail.value)}
              placeholder="e.g., https://example.com"
            />
          </FormField>
        </SpaceBetween>
      </Modal>
    </SpaceBetween>
  );
}
