import React, { useState, useEffect } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import AttributeEditor from "@cloudscape-design/components/attribute-editor";
import Input from "@cloudscape-design/components/input";
import FormField from "@cloudscape-design/components/form-field";
import Alert from "@cloudscape-design/components/alert";
import Table from "@cloudscape-design/components/table";
import Box from "@cloudscape-design/components/box";
import { api } from '../utils/api';

interface Header {
  key: string;
  value: string;
}

interface HeadersManagerProps {
  usecaseId: string;
}

export default function HeadersManager({ usecaseId }: HeadersManagerProps) {
  const [headers, setHeaders] = useState<Header[]>([]);
  const [existingHeaders, setExistingHeaders] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    fetchHeaders();
  }, [usecaseId]);

  const fetchHeaders = async () => {
    try {
      setLoading(true);
      const response = await api.get(`usecase/${usecaseId}/headers`);
      setExistingHeaders(response.headers || {});
      setError(null);
    } catch (error) {
      console.error('Failed to fetch headers:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveHeaders = async () => {
    if (headers.length === 0) {
      setError('Please add at least one header');
      return;
    }

    // Validate that all headers have both key and value
    const invalidHeaders = headers.filter(header => !header.key.trim() || !header.value.trim());
    if (invalidHeaders.length > 0) {
      setError('All headers must have both a key and value');
      return;
    }

    // Check for duplicate keys
    const keys = headers.map(h => h.key.trim());
    const duplicateKeys = keys.filter((key, index) => keys.indexOf(key) !== index);
    if (duplicateKeys.length > 0) {
      setError(`Duplicate header keys found: ${duplicateKeys.join(', ')}`);
      return;
    }

    setSaving(true);
    setError(null);

    try {
      // Convert array to map
      const headersMap: Record<string, string> = {};
      headers.forEach(h => {
        headersMap[h.key.trim()] = h.value.trim();
      });

      await api.post(`usecase/${usecaseId}/headers`, { headers: headersMap });
      setSuccess('Headers saved successfully');
      setHeaders([]); // Clear the form
      await fetchHeaders(); // Refresh the list
    } catch (error) {
      console.error('Failed to save headers:', error);
      setError('Failed to save headers');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteHeader = async (headerKey: string) => {
    setError(null);

    try {
      // Remove the header from the existing headers
      const updatedHeaders = { ...existingHeaders };
      delete updatedHeaders[headerKey];

      await api.post(`usecase/${usecaseId}/headers`, { headers: updatedHeaders });
      setSuccess(`Header "${headerKey}" deleted successfully`);
      await fetchHeaders(); // Refresh the list
    } catch (error) {
      console.error('Failed to delete header:', error);
      setError(`Failed to delete header "${headerKey}"`);
    }
  };

  const clearMessages = () => {
    setError(null);
    setSuccess(null);
  };

  return (
    <Container
      header={
        <Header
          variant="h2"
          description="Manage custom HTTP headers that will be sent with every request during workflow execution. Headers are stored in DynamoDB and applied before navigating to the starting URL."
          actions={
            <Button
              variant="primary"
              onClick={handleSaveHeaders}
              loading={saving}
              disabled={saving || headers.length === 0}
            >
              {saving ? 'Saving...' : 'Save Headers'}
            </Button>
          }
        />
      }
    >
      <SpaceBetween direction="vertical" size="l">
        {error && (
          <Alert
            type="error"
            dismissible
            onDismiss={clearMessages}
          >
            {error}
          </Alert>
        )}

        {success && (
          <Alert
            type="success"
            dismissible
            onDismiss={clearMessages}
          >
            {success}
          </Alert>
        )}

        <Header variant="h3">
          Current Headers
        </Header>
          {loading ? (
            <Box>Loading headers...</Box>
          ) : Object.keys(existingHeaders).length === 0 ? (
            <Box>No headers configured for this usecase.</Box>
          ) : (
            <Table
              columnDefinitions={[
                {
                  id: "key",
                  header: "Header Name",
                  cell: (item: [string, string]) => item[0]
                },
                {
                  id: "value",
                  header: "Header Value",
                  cell: (item: [string, string]) => item[1]
                },
                {
                  id: "actions",
                  header: "Actions",
                  cell: (item: [string, string]) => (
                    <Button
                      variant="link"
                      onClick={() => handleDeleteHeader(item[0])}
                    >
                      Delete
                    </Button>
                  )
                }
              ]}
              items={Object.entries(existingHeaders)}
              empty={
                <Box textAlign="center">
                  <b>No headers</b>
                  <Box variant="p" color="text-body-secondary">
                    No headers have been configured for this usecase.
                  </Box>
                </Box>
              }
            />
          )}

        <Header
          variant="h3"
        >
          Add New Headers
        </Header>
        <SpaceBetween direction="vertical" size="m">
          <AttributeEditor
            onAddButtonClick={() => setHeaders([...headers, { key: '', value: '' }])}
            onRemoveButtonClick={({
              detail: { itemIndex }
            }) => {
              const tmpItems = [...headers];
              tmpItems.splice(itemIndex, 1);
              setHeaders(tmpItems);
            }}
            items={headers}
            addButtonText="Add new header"
            removeButtonText="Remove"
            definition={[
              {
                label: "Header Name",
                control: (item: Header, itemIndex: number) => (
                  <FormField>
                    <Input
                      value={item.key}
                      onChange={({ detail }) => {
                        const tmpItems = [...headers];
                        tmpItems[itemIndex].key = detail.value;
                        setHeaders(tmpItems);
                      }}
                      placeholder="e.g., Authorization, X-Custom-Header"
                    />
                  </FormField>
                )
              },
              {
                label: "Header Value",
                control: (item: Header, itemIndex: number) => (
                  <FormField>
                    <Input
                      value={item.value}
                      onChange={({ detail }) => {
                        const tmpItems = [...headers];
                        tmpItems[itemIndex].value = detail.value;
                        setHeaders(tmpItems);
                      }}
                      placeholder="Enter the header value"
                    />
                  </FormField>
                )
              }
            ]}
          />
        </SpaceBetween>
      </SpaceBetween>
    </Container>
  );
}
