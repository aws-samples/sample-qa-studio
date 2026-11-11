import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import KeyValuePairs from "@cloudscape-design/components/key-value-pairs";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Badge from "@cloudscape-design/components/badge";
import Box from "@cloudscape-design/components/box";
import type { ExecutionVariablesResponse } from '../../utils/api';

interface ExecutionVariablesProps {
  /** The `/variables` response polled by `ExecutionDetailPanel`. */
  variables: ExecutionVariablesResponse;
}

/**
 * The Variables container of an execution. Presentational: the panel owns the fetch.
 * *Defined Variables* is the run's snapshot (`execution_variables`), not the use case's
 * current variables, so the values match what the run started with.
 */
export default function ExecutionVariables({ variables }: ExecutionVariablesProps) {
  const defined = Object.entries(variables.execution_variables ?? {}).map(([key, value]) => ({ key, value }));
  const runtime = variables.runtime_variables ?? [];

  if (defined.length === 0 && runtime.length === 0) {
    return (
      <Container header={<Header variant="h2">Variables</Header>}>
        <Box color="text-status-inactive">No variables defined for this execution</Box>
      </Container>
    );
  }

  return (
    <Container
      header={
        <Header variant="h2" counter={`(${defined.length + runtime.length})`}>
          Variables
        </Header>
      }
    >
      <SpaceBetween direction="vertical" size="l">
        {defined.length > 0 && (
          <div>
            <SpaceBetween direction="vertical" size="xs">
              <Header variant="h3">
                <SpaceBetween direction="horizontal" size="xs">
                  <span>Defined Variables</span>
                  <Badge color="blue">{defined.length}</Badge>
                </SpaceBetween>
              </Header>
              <KeyValuePairs
                columns={2}
                items={defined.map(variable => ({ label: variable.key, value: variable.value }))}
              />
            </SpaceBetween>
          </div>
        )}

        {runtime.length > 0 && (
          <div>
            <SpaceBetween direction="vertical" size="xs">
              <Header variant="h3">
                <SpaceBetween direction="horizontal" size="xs">
                  <span>Runtime Variables</span>
                  <Badge color="green">{runtime.length}</Badge>
                </SpaceBetween>
              </Header>
              <KeyValuePairs
                columns={2}
                items={runtime.map(variable => ({ label: variable.key, value: variable.value }))}
              />
            </SpaceBetween>
          </div>
        )}
      </SpaceBetween>
    </Container>
  );
}
