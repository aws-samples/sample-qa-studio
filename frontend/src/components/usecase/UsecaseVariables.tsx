import React, { useState, useEffect, useCallback } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import Button from "@cloudscape-design/components/button";
import SpaceBetween from "@cloudscape-design/components/space-between";
import AttributeEditor from "@cloudscape-design/components/attribute-editor";
import FormField from "@cloudscape-design/components/form-field";
import Input from "@cloudscape-design/components/input";
import ExpandableSection from "@cloudscape-design/components/expandable-section";
import Table from "@cloudscape-design/components/table";
import { api } from '../../utils/api';
import { ContainerLoading } from '../common/LoadingStates';

interface Variable {
  key: string;
  value: string;
}

interface UsecaseVariablesProps {
  usecaseId: string;
}

export default function UsecaseVariables({ usecaseId }: UsecaseVariablesProps) {
  const [variables, setVariables] = useState<Variable[]>([]);
  const [localVariables, setLocalVariables] = useState<Variable[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingVariables, setSavingVariables] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Async function to fetch variables data
  const fetchVariables = useCallback(async () => {
    if (!usecaseId) return;

    setLoading(true);
    setError(null);

    try {
      const response = await api.get(`usecase/${usecaseId}/variables`);
      const fetchedVariables = response.variables || [];
      setVariables(fetchedVariables);
      setLocalVariables(fetchedVariables);
    } catch (err: any) {
      console.error('Failed to fetch variables:', err);
      
      // Don't show error for 404 - just means no variables exist yet
      if (err?.response?.status === 404 || err?.status === 404) {
        setVariables([]);
        setLocalVariables([]);
      } else {
        setVariables([]);
        setLocalVariables([]);
      }
    } finally {
      setLoading(false);
    }
  }, [usecaseId]);

  // Fetch data when usecaseId changes
  useEffect(() => {
    fetchVariables();
  }, [usecaseId]);

  // Handle saving variables
  const handleUpdateVariables = useCallback(async () => {
    setSavingVariables(true);
    setError(null);

    try {
      await api.post(`usecase/${usecaseId}/variables`, { variables: localVariables });
      setVariables(localVariables); // Update the server state
      console.log('Variables saved successfully');
    } catch (err: any) {
      console.error('Failed to save variables:', err);
      
      // Provide more specific error messages
      if (err?.response?.status === 404 || err?.status === 404) {
        setError('Usecase not found. Please refresh the page.');
      } else if (err?.response?.status === 403 || err?.status === 403) {
        setError('You do not have permission to save variables.');
      } else {
        setError('Failed to save variables. Please try again.');
      }
    } finally {
      setSavingVariables(false);
    }
  }, [usecaseId, localVariables]);

  // Handle adding a new variable
  const handleAddVariable = useCallback(() => {
    setLocalVariables(prev => [...prev, { key: '', value: '' }]);
  }, []);

  // Handle removing a variable
  const handleRemoveVariable = useCallback((itemIndex: number) => {
    setLocalVariables(prev => {
      const newVariables = [...prev];
      newVariables.splice(itemIndex, 1);
      return newVariables;
    });
  }, []);

  // Handle updating a variable field
  const handleUpdateVariable = useCallback((itemIndex: number, field: 'key' | 'value', value: string) => {
    setLocalVariables(prev => {
      const newVariables = [...prev];
      newVariables[itemIndex][field] = value;
      return newVariables;
    });
  }, []);

  // Check if there are unsaved changes
  const hasUnsavedChanges = JSON.stringify(variables) !== JSON.stringify(localVariables);

  const predefinedVariables = [
    { key: "UniqueID", description: "Random 5-character string" },
    { key: "Time", description: "Current timestamp" },
    { key: "ExecutionID", description: "Current execution ID" },
    { key: "CreatedAt", description: "Execution creation time" }
  ];

  if (loading) {
    return (
      <ContainerLoading
        title="Workflow Variables"
        text="Loading variables..."
      />
    );
  }

  return (
    <Container
      header={
        <Header
          variant="h2"
          actions={
            <SpaceBetween direction="horizontal" size="xs">
              <Button
                iconName="refresh"
                onClick={fetchVariables}
                disabled={loading || savingVariables}
                ariaLabel="Refresh variables"
              />
              {hasUnsavedChanges && (
                <Button
                  variant="link"
                  onClick={() => setLocalVariables(variables)}
                >
                  Reset Changes
                </Button>
              )}
              <Button
                variant="primary"
                onClick={handleUpdateVariables}
                loading={savingVariables}
                disabled={savingVariables || !hasUnsavedChanges}
              >
                {savingVariables ? 'Saving...' : hasUnsavedChanges ? 'Save Changes' : 'Saved'}
              </Button>
            </SpaceBetween>
          }
        />
      }
    >
      <SpaceBetween direction="vertical" size="m">
        {error && (
          <div style={{
            padding: '12px',
            backgroundColor: '#ffeaea',
            border: '1px solid #ff6b6b',
            borderRadius: '4px',
            color: '#d63031'
          }}>
            {error}
          </div>
        )}

        <ExpandableSection headerText="Predefined Variables">
          <Table
            columnDefinitions={[
              {
                id: "key",
                header: "Variable",
                cell: item => `{{${item.key}}}`
              },
              {
                id: "description",
                header: "Description",
                cell: item => item.description || "-"
              }
            ]}
            items={predefinedVariables}
            empty="No predefined variables available."
          />
        </ExpandableSection>

        <ExpandableSection headerText="Custom Variables" defaultExpanded={true}>
          <AttributeEditor
            onAddButtonClick={handleAddVariable}
            onRemoveButtonClick={({ detail: { itemIndex } }) => handleRemoveVariable(itemIndex)}
            items={localVariables}
            addButtonText="Add new variable"
            removeButtonText="Remove"
            definition={[
              {
                label: "Key",
                control: (item: Variable, itemIndex: number) => (
                  <FormField>
                    <Input
                      value={item.key}
                      onChange={({ detail }) => handleUpdateVariable(itemIndex, 'key', detail.value)}
                      placeholder="Enter key"
                    />
                  </FormField>
                )
              },
              {
                label: "Value",
                control: (item: Variable, itemIndex: number) => (
                  <FormField>
                    <Input
                      value={item.value}
                      onChange={({ detail }) => handleUpdateVariable(itemIndex, 'value', detail.value)}
                      placeholder="Enter value"
                    />
                  </FormField>
                )
              }
            ]}
            empty="No variables configured. Click 'Add new variable' to get started."
          />
        </ExpandableSection>
      </SpaceBetween>
    </Container>
  );
}