import React, { useState } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import KeyValuePairs from "@cloudscape-design/components/key-value-pairs";
import StatusIndicator from "@cloudscape-design/components/status-indicator";
import CopyToClipboard from "@cloudscape-design/components/copy-to-clipboard";
import Button from "@cloudscape-design/components/button";
import { getVideoUrl } from '../../utils/s3Utils';

interface ExecutionInformationProps {
  execution: any;
  usecaseId: string;
  executionId: string;
  onViewVideo: (content: { url: string, title: string, fileType: string }) => void;
}

export default function ExecutionInformation({ 
  execution, 
  usecaseId, 
  executionId, 
  onViewVideo 
}: ExecutionInformationProps) {
  const [loadingVideo, setLoadingVideo] = useState(false);

  const handleViewVideo = async () => {
    try {
      setLoadingVideo(true);
      const { signedUrl } = await getVideoUrl(usecaseId, executionId);
      onViewVideo({
        url: signedUrl,
        title: 'Execution Video',
        fileType: 'video'
      });
    } catch (error) {
      console.error('Failed to load video file:', error);
    } finally {
      setLoadingVideo(false);
    }
  };

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
            value: <StatusIndicator type={execution.status}>
              {execution.status}
            </StatusIndicator>,
          },
          {
            label: "Created",
            value: new Date(execution.createdAt).toLocaleString(),
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
                onClick={handleViewVideo}
                loading={loadingVideo}
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