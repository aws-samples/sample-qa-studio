import { useState } from 'react';
import Header from '@cloudscape-design/components/header';
import Table from '@cloudscape-design/components/table';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Button from '@cloudscape-design/components/button';
import Modal from '@cloudscape-design/components/modal';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import CopyToClipboard from '@cloudscape-design/components/copy-to-clipboard';
import { api } from '../../utils/api';

interface ExecutionStepsProps {
  executionSteps: any[];
  usecaseId: string;
  executionId: string;
}

function getStatusType(status: string) {
  switch (status) {
    case 'success': return 'success';
    case 'error':
    case 'failed': return 'error';
    case 'executing': return 'in-progress';
    case 'pending': return 'pending';
    case 'cached': return 'success';
    default: return 'pending';
  }
}

export default function ExecutionSteps({
  executionSteps,
  usecaseId,
  executionId,
}: ExecutionStepsProps) {
  const [traceModalVisible, setTraceModalVisible] = useState(false);
  const [traceUrl, setTraceUrl] = useState<string | null>(null);
  const [traceLoading, setTraceLoading] = useState(false);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [traceTitle, setTraceTitle] = useState('');

  const handleTraceClick = async (step: any) => {
    const actId = step.actId || step.act_id;
    if (!actId || actId === 'cached' || actId === 'error') return;

    setTraceLoading(true);
    setTraceError(null);
    setTraceTitle(`Step ${step.sort}: ${actId}`);
    setTraceModalVisible(true);

    try {
      const result = await api.post('generate-s3-url', {
        usecaseId,
        executionId,
        fileType: 'html',
        actId,
      });
      if (result.signedUrl) {
        setTraceUrl(result.signedUrl);
      } else {
        setTraceError('No trace file found');
      }
    } catch (err: any) {
      setTraceError(err?.message || 'Failed to load trace');
    } finally {
      setTraceLoading(false);
    }
  };

  const handleCloseModal = () => {
    setTraceModalVisible(false);
    setTraceUrl(null);
    setTraceError(null);
  };

  return (
    <>
      <Table
        header={<Header variant="h2">Execution Steps</Header>}
        columnDefinitions={[
          {
            id: 'sort',
            header: 'Step',
            width: 70,
            cell: (item: any) => item.sort,
          },
          {
            id: 'status',
            header: 'Status',
            width: 100,
            cell: (item: any) => {
              return (
                <StatusIndicator type={getStatusType(item.status)}>
                  {item.status}
                </StatusIndicator>
              );
            },
          },
          {
            id: 'instruction',
            header: 'Instruction',
            cell: (item: any) => {
              const actId = item.actId || item.act_id;
              const hasTrace = actId && actId !== 'cached' && actId !== 'error';
              return (
                <SpaceBetween direction="vertical" size="xxs">
                  <span>{item.instruction}</span>
                  <SpaceBetween direction="horizontal" size="xs">
                    {hasTrace && (
                      <Button
                        variant="inline-link"
                        iconName="file"
                        onClick={() => handleTraceClick(item)}
                      >
                        Trace
                      </Button>
                    )}
                    {hasTrace && actId && (
                      <CopyToClipboard
                        copyButtonAriaLabel="Copy Act ID"
                        copyErrorText="failed to copy"
                        copySuccessText="copied"
                        textToCopy={actId}
                        variant="inline"
                      />
                    )}
                    {!hasTrace && actId === 'cached' && (
                      <Box fontSize="body-s" color="text-body-secondary">Executed from cache</Box>
                    )}
                  </SpaceBetween>
                  {item.logs && item.logs.length > 0 && (
                    <Box color="text-status-error" fontSize="body-s">
                      {item.logs}
                    </Box>
                  )}
                </SpaceBetween>
              );
            },
          },
          {
            id: 'validation',
            header: 'Validation',
            width: 200,
            cell: (item: any) => {
              if (!item.validation_type) return '-';
              return (
                <SpaceBetween direction="vertical" size="xxs">
                  <span>{item.validation_type}: {item.validation_operator} {item.validation_value}</span>
                  {item.actual_value && (
                    <Box fontSize="body-s" color="text-body-secondary">
                      Actual: {item.actual_value}
                    </Box>
                  )}
                </SpaceBetween>
              );
            },
          },
        ]}
        items={executionSteps}
        variant="container"
        stripedRows
        empty={<Box textAlign="center" padding="l">No steps found</Box>}
      />

      {/* Trace HTML Viewer Modal */}
      <Modal
        visible={traceModalVisible}
        onDismiss={handleCloseModal}
        header={traceTitle}
        size="max"
      >
        {traceLoading && (
          <Box textAlign="center" padding="l">
            <StatusIndicator type="loading">Loading trace...</StatusIndicator>
          </Box>
        )}
        {traceError && (
          <Box textAlign="center" padding="l" color="text-status-error">
            {traceError}
          </Box>
        )}
        {traceUrl && !traceLoading && (
          <iframe
            src={traceUrl}
            title="Nova Act Trace Viewer"
            style={{
              width: '100%',
              height: '80vh',
              border: 'none',
              borderRadius: '4px',
            }}
          />
        )}
      </Modal>
    </>
  );
}
