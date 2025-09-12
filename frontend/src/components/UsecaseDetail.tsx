import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Input from "@cloudscape-design/components/input";
import TokenGroup, { TokenGroupProps } from "@cloudscape-design/components/token-group";
import Button from "@cloudscape-design/components/button";
import Checkbox from "@cloudscape-design/components/checkbox";
import KeyValuePairs from "@cloudscape-design/components/key-value-pairs";
import FormField from "@cloudscape-design/components/form-field";
import Link from "@cloudscape-design/components/link";
import Textarea from "@cloudscape-design/components/textarea";
import Table from "@cloudscape-design/components/table";
import StatusIndicator from "@cloudscape-design/components/status-indicator";
import AttributeEditor from "@cloudscape-design/components/attribute-editor";
import CopyToClipboard from "@cloudscape-design/components/copy-to-clipboard";
import Select from "@cloudscape-design/components/select";
import ExpandableSection from "@cloudscape-design/components/expandable-section";
import ace from 'ace-builds';
import 'ace-builds/src-noconflict/mode-python';
import 'ace-builds/src-noconflict/theme-textmate';
import CodeEditor from "@cloudscape-design/components/code-editor";
import Badge from "@cloudscape-design/components/badge";

ace.config.set('basePath', 'https://cdn.jsdelivr.net/npm/ace-builds@1.43.2/src-noconflict/');
import { api, hooksApi, exportImportApi } from '../utils/api';
import SecretsManager from './SecretsManager';
import StepsTable from './StepsTable';

interface UsecaseStep {
  pk: string
  sk: string
  usecaseId: string
  sort: number
  instruction: string
  step_type?: string
  secret_key?: string
}

export default function UsecaseDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [usecase, setUsecase] = useState<any>(null);
  const [tags, setTags] = useState<string[]>([])
  const [loading, setLoading] = useState(true);
  const [steps, setSteps] = useState<UsecaseStep[]>([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [instruction, setInstruction] = useState('');
  const [stepType, setStepType] = useState('text');
  const [selectedSecret, setSelectedSecret] = useState('');
  const [availableSecrets, setAvailableSecrets] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [editingUsecase, setEditingUsecase] = useState(false);
  const [executions, setExecutions] = useState<any[]>([]);
  const [variables, setVariables] = useState<{ key: string, value: string }[]>([]);
  const [savingVariables, setSavingVariables] = useState(false);
  const [schedule, setSchedule] = useState<any>(null);
  const [showScheduleForm, setShowScheduleForm] = useState(false);
  const [rateValue, setRateValue] = useState('');
  const [rateUnit, setRateUnit] = useState('minutes');
  const [savingSchedule, setSavingSchedule] = useState(false);
  const [beforeScript, setBeforeScript] = useState('');
  const [afterScript, setAfterScript] = useState('');
  const [savingHooks, setSavingHooks] = useState(false);
  const [preferences, setPreferences] = useState({});
  const i18nStrings = {
    loadingState: 'Loading code editor',
    errorState: 'There was an error loading the code editor.',
    errorStateRecovery: 'Retry',

    editorGroupAriaLabel: 'Code editor',
    statusBarGroupAriaLabel: 'Status bar',

    cursorPosition: (row: any, column: any) => `Ln ${row}, Col ${column}`,
    errorsTab: 'Errors',
    warningsTab: 'Warnings',
    preferencesButtonAriaLabel: 'Preferences',

    paneCloseButtonAriaLabel: 'Close',

    preferencesModalHeader: 'Preferences',
    preferencesModalCancel: 'Cancel',
    preferencesModalConfirm: 'Confirm',
    preferencesModalWrapLines: 'Wrap lines',
    preferencesModalTheme: 'Theme',
    preferencesModalLightThemes: 'Light themes',
    preferencesModalDarkThemes: 'Dark themes',
  };

  const handleCreateSchedule = async () => {
    if (!rateValue.trim()) return;
    setSavingSchedule(true);
    try {
      await api.post(`usecase/${id}/schedule`, {
        rate: parseInt(rateValue),
        unit: rateUnit
      });
      setRateValue('');
      setShowScheduleForm(false);
      // Refresh schedule data
      const scheduleData = await api.get(`usecase/${id}/schedule`);
      setSchedule(scheduleData);
    } catch (error) {
      console.error('Failed to create schedule:', error);
    } finally {
      setSavingSchedule(false);
    }
  };

  const handleDeleteSchedule = async () => {
    try {
      await api.delete(`usecase/${id}/schedule`);
      setSchedule(null);
    } catch (error) {
      console.error('Failed to delete schedule:', error);
    }
  };

  const handleDeleteUsecase = async () => {
    await api.delete(`usecase/${id}`)
    navigate('/')
  }

  const handleExportUsecase = async () => {
    try {
      const blob = await exportImportApi.exportUsecase(id!);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = `usecase-${usecase.name}-export.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Failed to export usecase:', error);
    }
  }

  const handleUpdateVariables = async () => {
    setSavingVariables(true);
    try {
      await api.post(`usecase/${id}/variables`, { variables });
      console.log('Variables saved successfully');
    } catch (error) {
      console.error('Failed to save variables:', error);
    } finally {
      setSavingVariables(false);
    }
  }

  const handleSaveHooks = async () => {
    setSavingHooks(true);
    try {
      await hooksApi.create(id!, { before_script: beforeScript, after_script: afterScript });
      console.log('Hooks saved successfully');
    } catch (error) {
      console.error('Failed to save hooks:', error);
    } finally {
      setSavingHooks(false);
    }
  }

  const handleDeleteExecution = async (pk: string) => {
    const executionId = pk.replace('EXECUTION#', '')
    await api.delete(`usecase/${id}/executions/${executionId}`)
    await fetchData();
  }

  const fetchData = async () => {
    try {
      const [usecaseData, stepsData, variablesData, beforeScriptData] = await Promise.all([
        api.get(`usecase/${id}`),
        api.get(`usecase/${id}/steps`),
        api.get(`usecase/${id}/variables`),
        hooksApi.get(id!),
      ]);

      try {
        const scheduleData = await api.get(`usecase/${id}/schedule`)
        setSchedule(scheduleData);
      } catch (e) {
        console.info(e)
      }

      setTags(usecaseData.tags);
      setUsecase(usecaseData);
      setSteps(stepsData.steps || []);
      setVariables(variablesData.variables || []);
      setBeforeScript(beforeScriptData.before_script || '');
      setAfterScript(beforeScriptData.after_script || '');

    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setLoading(false);
    }
  };

  let fetchInterval: number
  const fetchExecutions = async () => {
    const executionsData = await api.get(`usecase/${id}/executions`)
    setExecutions(executionsData.executions || []);
  }

  const fetchSecrets = async () => {
    try {
      const secretsData = await api.get(`usecase/${id}/secrets`);
      setAvailableSecrets(secretsData.secrets || []);
    } catch (error) {
      console.error('Failed to fetch secrets:', error);
      setAvailableSecrets([]);
    }
  }

  useEffect(() => {
    fetchData();
    fetchExecutions();
    fetchSecrets();
  }, [id]);

  useEffect(() => {
    fetchInterval = window.setInterval(() => {
      fetchExecutions();
    }, 10000);

    return () => {
      if (fetchInterval) {
        clearInterval(fetchInterval);
      }
    };
  }, [])

  const handleExecute = async () => {
    setExecuting(true);
    try {
      await api.post(`usecase/${id}/execute?trigger-type=OnDemand`, { id });
      await fetchData();
      // Show success feedback
      console.log('Execution started successfully');
    } catch (error) {
      console.error('Failed to execute use case:', error);
    } finally {
      setExecuting(false);
    }
  };

  const handleUpdateStep = async (currentItem: UsecaseStep, _: any, value: unknown,) => {
    console.warn(currentItem, currentItem.sk.replace("STEP#", ""))
    await api.patch(`usecase/${id}/steps/${currentItem.sk.replace("STEP#", "")}`, {
      instruction: value,
    });
    await fetchData()
  }

  const reorderStepsSequentially = async () => {
    try {
      console.log('Reordering steps sequentially...');

      // Get current steps
      const updatedSteps = await api.get(`usecase/${id}/steps`);
      const stepsToReorder = updatedSteps.steps || [];

      console.log('Steps to reorder:', stepsToReorder.length);

      if (stepsToReorder.length > 0) {
        // Create step orders with sequential numbering
        const stepOrders = stepsToReorder
          .sort((a, b) => a.sort - b.sort) // Sort by current sort value
          .map((step, index) => ({
            step_id: step.sk,
            sort: index + 1 // Sequential numbering starting from 1
          }));

        console.log('Step orders:', stepOrders);

        // Call reorder API to update sort values
        await api.patch(`usecase/${id}/steps/reorder`, {
          step_orders: stepOrders
        });

        console.log('Steps reordered successfully');

        // Refresh data to show updated sort values
        await fetchData();
      }
    } catch (error) {
      console.error('Failed to reorder steps:', error);
    }
  };

  const handleDeleteStep = async (stepId: string) => {
    try {
      // Delete the step
      await api.delete(`usecase/${id}/steps/${stepId.replace("STEP#", "")}`);

      // Reorder remaining steps to maintain sequential numbering
      await reorderStepsSequentially();
    } catch (error) {
      console.error('Failed to delete step:', error);
    }
  }

  const handleAddStep = async () => {
    if (!instruction.trim()) return;
    if (stepType === 'secret' && !selectedSecret) return;

    setSaving(true);
    try {
      const stepData: any = {
        usecaseId: id!,
        sort: steps.length + 1,
        instruction: instruction.trim(),
        step_type: stepType
      };

      if (stepType === 'secret') {
        stepData.secret_key = selectedSecret;
      }

      await api.post(`/usecase/${id}/steps`, stepData);

      // Reload steps after adding
      const stepsData = await api.get(`/usecase/${id}/steps`);
      setSteps(stepsData.steps || []);

      setInstruction('');
      setStepType('text');
      setSelectedSecret('');
      setShowAddForm(false);
    } catch (error) {
      console.error('Failed to add step:', error);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div>Loading...</div>;
  if (!usecase) return <div>Use case not found</div>;

  return (
    <SpaceBetween direction="vertical" size="l">
      <Header
        variant="h1"
        actions={
          <SpaceBetween direction="horizontal" size="m">
            <Button onClick={() => navigate('/')}>
              Back to Use Cases
            </Button>

            <Button onClick={handleExportUsecase}>
              Export Usecase
            </Button>

            <Button variant="primary" onClick={handleExecute} loading={executing} disabled={executing}>
              {executing ? 'Starting Execution...' : 'Trigger Execution'}
            </Button>
          </SpaceBetween>
        }
      >
        {usecase.name}
      </Header>

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
            onSave={async (updatedUsecase) => {
              await api.patch(`usecase/${id}`, updatedUsecase);
              await fetchData();
              setEditingUsecase(false);
            }}
            onCancel={() => setEditingUsecase(false)}
          />
        ) : (
          <KeyValuePairs
            columns={3}
            items={[
              {
                label: "Name",
                value: usecase.name,
              }, {
                label: "ID",
                value: (<CopyToClipboard
                  copyButtonAriaLabel="Copy ID"
                  copyErrorText="ID failed to copy"
                  copySuccessText="ID copied"
                  textToCopy={usecase.id}
                  variant="inline"
                />),
              }, {
                label: "Description",
                value: usecase.description,
              }, {
                label: "Active",
                value: usecase.active ? 'Yes' : 'No',
              }, {
                label: "Starting URL",
                value: (<Link external href={usecase.starting_url}>{usecase.starting_url}</Link>),
              }, {
                label: "Created",
                value: new Date(usecase.createdAt).toLocaleDateString(),
              }, {
                label: "Headless Mode",
                value: usecase.headless ? 'Yes' : 'No',
              }, {
                label: "Tags",
                value: tags.map((tag: string) => (<Badge key={tag}>{tag}</Badge>)),
              }]
            }
          />
        )}
      </Container>

      <Container
        header={
          <Header
            variant="h2"
            actions={
              !schedule && (
                <Button onClick={() => setShowScheduleForm(!showScheduleForm)}>
                  {showScheduleForm ? 'Cancel' : 'Add Schedule'}
                </Button>
              )
            }
          >
            Schedule
          </Header>
        }
      >
        {showScheduleForm && (
          <SpaceBetween direction="vertical" size="m">
            <SpaceBetween direction="horizontal" size="s">
              <FormField label="Run every">
                <Input
                  value={rateValue}
                  onChange={({ detail }) => setRateValue(detail.value)}
                  placeholder="1"
                  type="number"
                />
              </FormField>
              <FormField label="Unit">
                <Select
                  selectedOption={{ label: rateUnit, value: rateUnit }}
                  onChange={({ detail }) => setRateUnit(detail.selectedOption.value!)}
                  options={[
                    { label: 'minutes', value: 'minutes' },
                    { label: 'hours', value: 'hours' },
                    { label: 'days', value: 'days' }
                  ]}
                />
              </FormField>
            </SpaceBetween>
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="primary" onClick={handleCreateSchedule} loading={savingSchedule} disabled={!rateValue.trim() || savingSchedule}>
                {savingSchedule ? 'Creating...' : 'Create Schedule'}
              </Button>
              <Button onClick={() => { setShowScheduleForm(false); setRateValue(''); }}>
                Cancel
              </Button>
            </SpaceBetween>
          </SpaceBetween>
        )}

        {schedule ? (
          <KeyValuePairs
            columns={2}
            items={[
              {
                label: "Rate",
                value: `Every ${schedule.rate} ${schedule.unit}`,
              },
              {
                label: "Status",
                value: schedule.enabled ? 'Enabled' : 'Disabled',
              },
              {
                label: "Actions",
                value: <Link onClick={handleDeleteSchedule}>Delete</Link>,
              }
            ]}
          />
        ) : (
          <div>No schedule configured. Click 'Add Schedule' to create a schedule.</div>
        )}
      </Container>

      <Container
        header={
          <Header
            variant="h2"
            actions={
              <Button onClick={handleSaveHooks} loading={savingHooks} disabled={savingHooks}>
                {savingHooks ? 'Saving...' : 'Save'}
              </Button>
            }
          >
            Hooks
          </Header>
        }
      >
        <SpaceBetween direction="vertical" size="m">
          <ExpandableSection headerText="Before hook">
            <FormField description="Execute code before the workflow execution, within the same shell">
              <CodeEditor
                ace={ace}
                language="python"
                value={beforeScript}
                onChange={({ detail }) => setBeforeScript(detail.value)}
                preferences={preferences}
                onPreferencesChange={(e) => setPreferences(e.detail)}
                editorContentHeight={100}
                loading={false}
              />
            </FormField>
          </ExpandableSection>
          <ExpandableSection headerText="After hook">
            <FormField description="Execute code after the workflow execution, within the same shell">
              <CodeEditor
                ace={ace}
                language="python"
                value={afterScript}
                onChange={({ detail }) => setAfterScript(detail.value)}
                preferences={preferences}
                onPreferencesChange={(e) => setPreferences(e.detail)}
                editorContentHeight={100}
                loading={false}
              />
            </FormField>
          </ExpandableSection>
        </SpaceBetween>
      </Container>

      <Container
        header={
          <Header
            variant="h2"
            actions={
              <Button onClick={handleUpdateVariables} loading={savingVariables} disabled={savingVariables}>
                {savingVariables ? 'Saving...' : 'Save'}
              </Button>
            }
          >
            Workflow Variables
          </Header>
        }
      >
        <SpaceBetween direction="vertical" size="m">
          <ExpandableSection headerText="Predefined Variables">
            <Table
              columnDefinitions={[
                {
                  id: "variable",
                  header: "Variable name",
                  cell: item => item.name,
                  isRowHeader: true
                },
                {
                  id: "description",
                  header: "Description",
                  cell: item => item.description || "-"
                }
              ]}
              items={[
                {
                  name: "UniqueID",
                  description: "A five character unique id that is stable throughout one execution",
                },
                {
                  name: "ExecutionID",
                  description: "The UUIDv4 that is generated for for a specific execution of the workflow",
                },
                {
                  name: "CreatedAt",
                  description: "Timestamp of the execution create date",
                },
                {
                  name: "Time",
                  description: "RFC3339 representation of the current time",
                },
              ]}
              sortingDisabled
              variant="embedded"
            />
          </ExpandableSection>

          <ExpandableSection headerText="Custom Variables" defaultExpanded={true}>
            <AttributeEditor
              onAddButtonClick={() => setVariables([...variables, { key: '', value: '' }])}
              onRemoveButtonClick={({
                detail: { itemIndex }
              }) => {
                const tmpItems = [...variables];
                tmpItems.splice(itemIndex, 1);
                setVariables(tmpItems);
              }}
              items={variables}
              addButtonText="Add new variable"
              removeButtonText="Remove"
              definition={[
                {
                  label: "Variable",
                  control: (item, itemIndex) => (
                    <Input
                      value={item.key}
                      onChange={({ detail }) => {
                        const tmpItems = [...variables];
                        tmpItems[itemIndex].key = detail.value;
                        setVariables(tmpItems);
                      }}
                      placeholder="Enter key"
                    />
                  )
                },
                {
                  label: "Value",
                  control: (item, itemIndex) => (
                    <Input
                      value={item.value}
                      onChange={({ detail }) => {
                        const tmpItems = [...variables];
                        tmpItems[itemIndex].value = detail.value;
                        setVariables(tmpItems);
                      }}
                      placeholder="Enter value"
                    />
                  )
                }
              ]}
              empty="No items associated with the resource."
            />
          </ExpandableSection>
        </SpaceBetween>
      </Container>

      <SecretsManager usecaseId={id!} />

      <Container
        header={
          <Header
            variant="h2"
            actions={
              <Button onClick={() => setShowAddForm(!showAddForm)}>
                {showAddForm ? 'Cancel' : 'Add Step'}
              </Button>
            }
          >
            Workflow Steps
          </Header>
        }
      >
        {showAddForm && (
          <SpaceBetween direction="vertical" size="m">
            <FormField label="Step Type">
              <Select
                selectedOption={{ label: stepType === 'text' ? 'Plain Text Step' : 'Secret Step', value: stepType }}
                onChange={({ detail }) => {
                  setStepType(detail.selectedOption.value!);
                  setSelectedSecret(''); // Reset secret selection when changing type
                }}
                options={[
                  { label: 'Plain Text Step', value: 'text' },
                  { label: 'Secret Step', value: 'secret' }
                ]}
              />
            </FormField>

            <FormField label={stepType === 'secret' ? 'Action Description' : 'Instruction'}>
              <Textarea
                value={instruction}
                onChange={({ detail }) => setInstruction(detail.value)}
                placeholder={stepType === 'secret' ? 'Describe the action (e.g., "Type password in login field")' : 'Enter step instruction'}
                rows={3}
              />
            </FormField>

            {stepType === 'secret' && (
              <FormField
                label="Select Secret"
                description="Choose which secret to use for this step"
              >
                <Select
                  selectedOption={selectedSecret ? { label: selectedSecret, value: selectedSecret } : null}
                  onChange={({ detail }) => setSelectedSecret(detail.selectedOption.value!)}
                  options={availableSecrets.map(secret => ({
                    label: secret.key,
                    value: secret.key
                  }))}
                  placeholder="Choose a secret..."
                  empty="No secrets available. Please add secrets first."
                />
              </FormField>
            )}

            <SpaceBetween direction="horizontal" size="xs">
              <Button
                variant="primary"
                onClick={handleAddStep}
                loading={saving}
                disabled={!instruction.trim() || saving || (stepType === 'secret' && !selectedSecret)}
              >
                Save Step
              </Button>
              <Button onClick={() => {
                setShowAddForm(false);
                setInstruction('');
                setStepType('text');
                setSelectedSecret('');
              }}>
                Cancel
              </Button>
            </SpaceBetween>
          </SpaceBetween>
        )}

        <StepsTable
          steps={steps}
          onStepsReordered={fetchData}
          onUpdateStep={handleUpdateStep}
          onDeleteStep={handleDeleteStep}
          usecaseId={id!}
        />
      </Container>

      <Container header={<Header variant="h2">Execution History</Header>}>
        <Table
          variant="embedded"
          columnDefinitions={[
            {
              id: 'pk',
              header: 'Execution ID',
              cell: item => (
                <Link onClick={() => navigate(`/usecase/${id}/execution/${item.sk.replace('EXECUTION#', '')}`)}>
                  {item.sk.replace('EXECUTION#', '')}
                </Link>
              ),
            },
            {
              id: 'status',
              header: 'Status',
              cell: item => (
                <StatusIndicator type={item.status === 'success' ? 'success' : item.status === 'error' ? 'error' : item.status === 'in-progress' ? 'in-progress' : 'pending'}>
                  {item.status || 'pending'}
                </StatusIndicator>
              ),
            },
            {
              id: 'triggerType',
              header: 'Triggered by',
              cell: item => item.triggerType,
            },
            {
              id: 'createdAt',
              header: 'Created',
              cell: item => new Date(item.createdAt).toLocaleString(),
            },
            {
              id: 'actions',
              header: 'Actions',
              cell: item => (
                <Link onClick={() => handleDeleteExecution(item.sk)}>Delete</Link>
              ),
            }
          ]}
          items={executions}
          empty="No executions found for this use case."
        />
      </Container>
      <Button variant="link" onClick={handleDeleteUsecase}>Delete use case</Button>
    </SpaceBetween>
  );
}

function EditUsecaseForm({ usecase, onSave, onCancel }: { usecase: any, onSave: (data: any) => void, onCancel: () => void }) {
  const [name, setName] = useState(usecase.name);
  const [description, setDescription] = useState(usecase.description);
  const [startingUrl, setStartingUrl] = useState(usecase.starting_url);
  const [active, setActive] = useState(usecase.active);
  const [headless, setHeadless] = useState(usecase.headless || false);
  const [tags, setTags] = useState(usecase.tags?.join(', ') || '');

  const handleSave = () => {
    onSave({
      name,
      description,
      starting_url: startingUrl,
      active,
      headless,
      tags: tags.split(',').map((tag: string) => tag.trim()).filter((tag: string) => tag)
    });
  };

  return (
    <SpaceBetween direction="vertical" size="m">
      <FormField label="Name">
        <Input value={name} onChange={({ detail }) => setName(detail.value)} />
      </FormField>
      <FormField label="Description">
        <Textarea value={description} onChange={({ detail }) => setDescription(detail.value)} rows={3} />
      </FormField>
      <FormField label="Starting URL">
        <Input value={startingUrl} onChange={({ detail }) => setStartingUrl(detail.value)} />
      </FormField>
      <FormField label="Tags">
        <Input value={tags} onChange={({ detail }) => setTags(detail.value)} placeholder="Enter tags separated by commas" />
      </FormField>
      <FormField>
        <Checkbox checked={headless} onChange={({ detail }) => setHeadless(detail.checked)}>Headless Mode</Checkbox>
      </FormField>
      <SpaceBetween direction="horizontal" size="xs">
        <Button variant="primary" onClick={handleSave}>Save</Button>
        <Button onClick={onCancel}>Cancel</Button>
      </SpaceBetween>
    </SpaceBetween>
  );
}