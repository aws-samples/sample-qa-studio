import { useState, useEffect } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import KeyValuePairs from "@cloudscape-design/components/key-value-pairs";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Badge from "@cloudscape-design/components/badge";
import Box from "@cloudscape-design/components/box";
import { api } from '../../utils/api';

interface ExecutionVariablesProps {
  usecaseId: string;
  executionId: string;
}

interface Variable {
  key: string;
  value: string;
}

interface ExecutionVariablesData {
  variables: Variable[];
  runtime_variables: Variable[];
}

export default function ExecutionVariables({ usecaseId, executionId }: ExecutionVariablesProps) {
  const [variablesData, setVariablesData] = useState<ExecutionVariablesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchVariables = async () => {
      try {
        setLoading(true);
        const data = await api.get(`usecase/${usecaseId}/executions/${executionId}/variables`);
        setVariablesData(data);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch execution variables:', err);
        setError('Failed to load execution variables');
      } finally {
        setLoading(false);
      }
    };

    fetchVariables();
  }, [usecaseId, executionId]);

  if (loading) {
    return (
      <Container header={<Header variant="h2">Variables</Header>}>
        <Box>Loading variables...</Box>
      </Container>
    );
  }

  if (error) {
    return (
      <Container header={<Header variant="h2">Variables</Header>}>
        <Box color="text-status-error">{error}</Box>
      </Container>
    );
  }

  const hasDefinedVariables = variablesData?.variables && variablesData.variables.length > 0;
  const hasRuntimeVariables = variablesData?.runtime_variables && variablesData.runtime_variables.length > 0;

  if (!hasDefinedVariables && !hasRuntimeVariables) {
    return (
      <Container header={<Header variant="h2">Variables</Header>}>
        <Box color="text-status-inactive">No variables defined for this execution</Box>
      </Container>
    );
  }

  return (
    <Container 
      header={
        <Header 
          variant="h2"
          counter={`(${(variablesData?.variables?.length || 0) + (variablesData?.runtime_variables?.length || 0)})`}
        >
          Variables
        </Header>
      }
    >
      <SpaceBetween direction="vertical" size="l">
        {hasDefinedVariables && (
          <div>
            <SpaceBetween direction="vertical" size="xs">
              <Header variant="h3">
                <SpaceBetween direction="horizontal" size="xs">
                  <span>Defined Variables</span>
                  <Badge color="blue">{variablesData.variables.length}</Badge>
                </SpaceBetween>
              </Header>
              <KeyValuePairs
                columns={2}
                items={variablesData.variables.map(variable => ({
                  label: variable.key,
                  value: variable.value
                }))}
              />
            </SpaceBetween>
          </div>
        )}

        {hasRuntimeVariables && (
          <div>
            <SpaceBetween direction="vertical" size="xs">
              <Header variant="h3">
                <SpaceBetween direction="horizontal" size="xs">
                  <span>Runtime Variables</span>
                  <Badge color="green">{variablesData.runtime_variables.length}</Badge>
                </SpaceBetween>
              </Header>
              <KeyValuePairs
                columns={2}
                items={variablesData.runtime_variables.map(variable => ({
                  label: variable.key,
                  value: variable.value
                }))}
              />
            </SpaceBetween>
          </div>
        )}
      </SpaceBetween>
    </Container>
  );
}