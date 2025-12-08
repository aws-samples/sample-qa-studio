import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import KeyValuePairs from "@cloudscape-design/components/key-value-pairs";
import StatusIndicator from "@cloudscape-design/components/status-indicator";
import CopyToClipboard from "@cloudscape-design/components/copy-to-clipboard";
import Button from "@cloudscape-design/components/button";

interface ExecutionInformationProps {
  execution: any;
  usecaseId: string;
  executionId: string;
  onViewRecording: () => void;
}

// Helper function to map execution status to StatusIndicator type
function getStatusType(status: string) {
  switch (status) {
    case 'success': return 'success';
    case 'error': 
    case 'failed': return 'error';
    case 'executing': return 'in-progress';
    case 'pending': return 'pending';
    case 'stopped': return 'stopped';
    default: return 'pending';
  }
}

export default function ExecutionInformation({ 
  execution, 
  usecaseId, 
  executionId, 
  onViewRecording 
}: ExecutionInformationProps) {

  return (
    <Container 
      header={
        <Header variant="h2">Execution Information</Header>
      }>
      <KeyValuePairs
        columns={2}
        items={[
          {
            label: "Execution ID",
            value: (
              <CopyToClipboard
                copyButtonAriaLabel="Copy Execution ID"
                copyErrorText="failed to copy"
                copySuccessText="copied"
                textToCopy={execution.sk.replace('EXECUTION#', '')}
                variant="inline"
              />
            ),
          },
          {
            label: "Status",
            value: <StatusIndicator type={getStatusType(execution.status)}>
              {execution.status}
            </StatusIndicator>,
          },
          {
            label: "Created",
            value: new Date(execution.createdAt).toLocaleString(),
          },
          {
            label: "Execution Region",
            value: execution.region,
          },
          {
            label: "Starting URL",
            value: (<a href={execution.starting_url} target="_startPage">{execution.starting_url}</a>),
          },
          {
            label: "NovaAct Session ID",
            value: (
              <CopyToClipboard
                copyButtonAriaLabel="Copy NovaAct Session ID"
                copyErrorText="failed to copy"
                copySuccessText="copied"
                textToCopy={execution.novaActSessionId}
                variant="inline"
              />
            ),
          },
          {
            label: "Recording",
            value: execution.novaActSessionId ? (
              <Button
                variant="inline-link"
                iconName="play"
                onClick={onViewRecording}
              >
                View
              </Button>
            ) : 'Not Available',
          }
        ]}
      />
    </Container>
  );
}