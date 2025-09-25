import React, { useState } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import Table from "@cloudscape-design/components/table";
import Button from "@cloudscape-design/components/button";
import CopyToClipboard from "@cloudscape-design/components/copy-to-clipboard";
import StatusIndicatorCompact from '../common/StatusIndicatorCompact';
import ValidationResult from '../common/ValidationResult';
import { getS3FileUrl } from '../../utils/s3Utils';

interface ExecutionStepsProps {
  executionSteps: any[];
  usecaseId: string;
  executionId: string;
  onViewFile: (content: { url: string, title: string, fileType: string }) => void;
}

export default function ExecutionSteps({
  executionSteps,
  usecaseId,
  executionId,
  onViewFile
}: ExecutionStepsProps) {
  const [loadingModal, setLoadingModal] = useState(false);

  const handleViewFile = async (item: any) => {
    try {
      setLoadingModal(true);
      const actId = item.actId || item.act_id;
      const { signedUrl, fileName } = await getS3FileUrl(usecaseId, executionId, actId, 'html');
      onViewFile({
        url: signedUrl,
        title: `Step ${item.sort}: ${fileName}`,
        fileType: 'html'
      });
    } catch (error) {
      console.error('Failed to load HTML file:', error);
    } finally {
      setLoadingModal(false);
    }
  };

  return (
    <Container header={<Header variant="h2">Execution Steps</Header>}>
      <Table
        resizableColumns
        variant="embedded"
        columnDefinitions={[
          {
            id: 'sort',
            header: 'Step',
            cell: item => item.sort,
            minWidth: 10,
            width: 45,
          },
          {
            id: 'status',
            header: 'Status',
            minWidth: 10,
            width: 80,
            cell: item => {
              const status = item.status || 'pending';
              return (
                <StatusIndicatorCompact status={status} />
              );
            },
          },
          {
            id: 'instruction',
            minWidth: 10,
            header: 'Instruction',
            cell: item => {
              const actId = item.actId || item.act_id;
              return (
                <div>
                  <div style={{ marginBottom: '4px' }}>
                    {item.instruction}
                  </div>
                  {actId && actId !== "error" && (
                    <div style={{ fontSize: '12px', color: '#5f6b7a', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Button
                        variant="inline-link"
                        iconName="file-open"
                        ariaLabel="View HTML file"
                        onClick={() => handleViewFile(item)}
                        loading={loadingModal}
                      >
                        Trace
                      </Button>
                      <CopyToClipboard
                        copyButtonAriaLabel="Copy Act ID"
                        copyErrorText="failed to copy"
                        copySuccessText="copied"
                        textToCopy={actId}
                        variant="inline"
                      />
                    </div>
                  )}
                </div>
              );
            },
            width: 500,
          },
          {
            id: 'logs',
            header: 'Validation',
            cell: item => {
              if ((item.stepType == 'validation' || item.stepType == 'assertion') && item.actualValue) {
                return (
                  <ValidationResult
                    validationType={item.validationType}
                    validationOperator={item.validationOperator}
                    validationValue={item.validationValue}
                    actualValue={item.actualValue}
                    status={item.status || 'pending'}
                  />
                );
              }

              if (item.logs) {
                return (<pre>{item.logs}</pre>)
              }

              return null;
            },
          },
        ]}
        items={executionSteps}
        empty="No execution steps found."
      />
    </Container>
  );
}