import { useState, useEffect } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import Table from "@cloudscape-design/components/table";
import Button from "@cloudscape-design/components/button";
import Alert from "@cloudscape-design/components/alert";
import SpaceBetween from "@cloudscape-design/components/space-between";
import { api } from '../../utils/api';
import { fetchAuthSession } from 'aws-amplify/auth';

interface DownloadedFile {
  fileName: string;
  size: number;
  lastModified: string;
}

interface DownloadedFilesProps {
  usecaseId: string;
  executionId: string;
  refreshTrigger?: number;
  executionRegion?: string;
}

export default function DownloadedFiles({ usecaseId, executionId, refreshTrigger, executionRegion }: DownloadedFilesProps) {
  const [files, setFiles] = useState<DownloadedFile[]>([]);
  const [loading, setLoading] = useState(true);
  const isCrossRegion = executionRegion && executionRegion !== __APP_CONFIG__.defaultRegion;

  useEffect(() => {
    fetchDownloads();
  }, [usecaseId, executionId, refreshTrigger]);

  const fetchDownloads = async () => {
    try {
      setLoading(true);
      const response = await api.get(`usecase/${usecaseId}/executions/${executionId}/downloads`);
      setFiles(response.files || []);
    } catch (error) {
      console.error('Failed to fetch downloads:', error);
      setFiles([]);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async (fileName: string) => {
    try {
      // Get the auth token
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();

      if (!token) {
        console.error('No authentication token available');
        return;
      }

      // Construct download URL
      const downloadUrl = `${__APP_CONFIG__.apiEndpoint}usecase/${usecaseId}/executions/${executionId}/downloads/${encodeURIComponent(fileName)}`;

      // Make a fetch request with auth header - the Lambda will redirect to presigned URL
      const response = await fetch(downloadUrl, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
        redirect: 'manual' // Don't follow redirects automatically
      });

      // Get the redirect location
      const location = response.headers.get('Location');
      if (location) {
        window.open(location, '_blank');
      }
    } catch (error) {
      console.error('Failed to download file:', error);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  if (loading) {
    return null;
  }

  if (files.length === 0) {
    return null;
  }

  return (
    <Container header={<Header variant="h2">Downloaded Files</Header>}>
      <SpaceBetween size="m">
        {isCrossRegion && (
          <Alert type="info" header="Cross-Region Replication">
            This execution ran in {executionRegion}, which is different from the default region ({__APP_CONFIG__.defaultRegion}). 
            Downloaded files are being replicated to the default region and may take a few minutes to appear.
          </Alert>
        )}
        <Table
          variant="embedded"
          columnDefinitions={[
          {
            id: 'fileName',
            header: 'File Name',
            cell: item => item.fileName,
            width: 300,
          },
          {
            id: 'size',
            header: 'Size',
            cell: item => formatFileSize(item.size),
            width: 100,
          },
          {
            id: 'lastModified',
            header: 'Downloaded At',
            cell: item => formatDate(item.lastModified),
            width: 200,
          },
          {
            id: 'actions',
            header: 'Actions',
            cell: item => (
              <Button
                variant="icon"
                iconName="download"
                onClick={() => handleDownload(item.fileName)}
              >
                Download
              </Button>
            ),
            width: 150,
          },
        ]}
        items={files}
        empty="No files downloaded."
        />
      </SpaceBetween>
    </Container>
  );
}
