import { useState, useEffect, useCallback } from 'react';
import Spinner from "@cloudscape-design/components/spinner";
import Alert from "@cloudscape-design/components/alert";
import Button from "@cloudscape-design/components/button";
import Box from "@cloudscape-design/components/box";
import { CodeView } from "@cloudscape-design/code-view";

export interface LogViewerProps {
  downloadUrl: string | null;
  loading?: boolean;
}

export default function LogViewer({ downloadUrl, loading: externalLoading }: LogViewerProps) {
  const [content, setContent] = useState<string | null>(null);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const fetchLog = useCallback(async (url: string) => {
    setFetching(true);
    setError(null);
    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Failed to fetch log: ${response.status} ${response.statusText}`);
      }
      const text = await response.text();
      setContent(text);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch log content';
      setError(message);
    } finally {
      setFetching(false);
    }
  }, []);

  useEffect(() => {
    if (downloadUrl) {
      fetchLog(downloadUrl);
    }
  }, [downloadUrl, fetchLog]);

  if (externalLoading || !downloadUrl || fetching) {
    return (
      <Box textAlign="center" padding="l">
        <Spinner size="large" />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert
        type="error"
        header="Failed to load logs"
        action={
          <Button onClick={() => fetchLog(downloadUrl)}>Retry</Button>
        }
      >
        {error}
      </Alert>
    );
  }

  if (content === null) {
    return null;
  }

  return (
    <div>
      <div style={{
        maxHeight: expanded ? 'none' : '200px',
        overflow: 'auto',
      }}>
        <CodeView
          content={content}
          lineNumbers
        />
      </div>
      <Box textAlign="center" padding={{ top: 'xs' }}>
        <Button
          variant="inline-link"
          iconName={expanded ? 'angle-up' : 'angle-down'}
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? 'Collapse' : 'Expand'}
        </Button>
      </Box>
    </div>
  );
}
