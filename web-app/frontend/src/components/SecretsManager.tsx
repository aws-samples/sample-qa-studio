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

interface Secret {
  key: string;
  value: string;
}

interface SecretInfo {
  key: string;
  secret_name: string;
  description: string;
  created_at: string;
}

interface SecretsManagerProps {
  usecaseId: string;
}

export default function SecretsManager({ usecaseId }: SecretsManagerProps) {
  const [secrets, setSecrets] = useState<Secret[]>([]);
  const [existingSecrets, setExistingSecrets] = useState<SecretInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    fetchSecrets();
  }, [usecaseId]);

  const fetchSecrets = async () => {
    try {
      setLoading(true);
      const response = await api.get(`usecase/${usecaseId}/secrets`);
      setExistingSecrets(response.secrets || []);
      setError(null);
    } catch (error) {
      console.error('Failed to fetch secrets:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveSecrets = async () => {
    if (secrets.length === 0) {
      setError('Please add at least one secret');
      return;
    }

    // Validate that all secrets have both key and value
    const invalidSecrets = secrets.filter(secret => !secret.key.trim() || !secret.value.trim());
    if (invalidSecrets.length > 0) {
      setError('All secrets must have both a key and value');
      return;
    }

    // Check for duplicate keys
    const keys = secrets.map(s => s.key.trim());
    const duplicateKeys = keys.filter((key, index) => keys.indexOf(key) !== index);
    if (duplicateKeys.length > 0) {
      setError(`Duplicate secret keys found: ${duplicateKeys.join(', ')}`);
      return;
    }

    setSaving(true);
    setError(null);

    try {
      await api.post(`usecase/${usecaseId}/secrets`, { secrets });
      setSuccess('Secrets saved successfully');
      setSecrets([]); // Clear the form
      await fetchSecrets(); // Refresh the list
    } catch (error) {
      console.error('Failed to save secrets:', error);
      setError('Failed to save secrets');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteSecret = async (secretKey: string) => {
    setDeleting(secretKey);
    setError(null);

    try {
      await api.delete(`usecase/${usecaseId}/secrets`, {
        secret_key: secretKey
      });
      setSuccess(`Secret "${secretKey}" deleted successfully`);
      await fetchSecrets(); // Refresh the list
    } catch (error) {
      console.error('Failed to delete secret:', error);
      setError(`Failed to delete secret "${secretKey}"`);
    } finally {
      setDeleting(null);
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
          description="Manage sensitive data like passwords, API keys, and tokens. Secrets are stored securely in AWS Secrets Manager and can be referenced in your secret steps when designing your workflow."
          actions={
            <Button
              variant="primary"
              onClick={handleSaveSecrets}
              loading={saving}
              disabled={saving || secrets.length === 0}
            >
              {saving ? 'Saving...' : 'Save Secrets'}
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
          Current Secrets
        </Header>
          {loading ? (
            <Box>Loading secrets...</Box>
          ) : existingSecrets.length === 0 ? (
            <Box>No secrets configured for this usecase.</Box>
          ) : (
            <Table
              columnDefinitions={[
                {
                  id: "key",
                  header: "Secret Key",
                  cell: (item: SecretInfo) => item.key
                },
                {
                  id: "actions",
                  header: "Actions",
                  cell: (item: SecretInfo) => (
                    <Button
                      variant="link"
                      loading={deleting === item.key}
                      onClick={() => handleDeleteSecret(item.key)}
                    >
                      Delete
                    </Button>
                  )
                }
              ]}
              items={existingSecrets}
              empty={
                <Box textAlign="center">
                  <b>No secrets</b>
                  <Box variant="p" color="text-body-secondary">
                    No secrets have been configured for this usecase.
                  </Box>
                </Box>
              }
            />
          )}

        <Header
          variant="h3"
        >
          Add New Secrets
        </Header>
        <SpaceBetween direction="vertical" size="m">
          <AttributeEditor
            onAddButtonClick={() => setSecrets([...secrets, { key: '', value: '' }])}
            onRemoveButtonClick={({
              detail: { itemIndex }
            }) => {
              const tmpItems = [...secrets];
              tmpItems.splice(itemIndex, 1);
              setSecrets(tmpItems);
            }}
            items={secrets}
            addButtonText="Add new secret"
            removeButtonText="Remove"
            definition={[
              {
                label: "Secret Key",
                control: (item: Secret, itemIndex: number) => (
                  <FormField>
                    <Input
                      value={item.key}
                      onChange={({ detail }) => {
                        const tmpItems = [...secrets];
                        tmpItems[itemIndex].key = detail.value;
                        setSecrets(tmpItems);
                      }}
                      placeholder="e.g., api_key, password, token"
                    />
                  </FormField>
                )
              },
              {
                label: "Secret Value",
                control: (item: Secret, itemIndex: number) => (
                  <FormField>
                    <Input
                      type="password"
                      value={item.value}
                      onChange={({ detail }) => {
                        const tmpItems = [...secrets];
                        tmpItems[itemIndex].value = detail.value;
                        setSecrets(tmpItems);
                      }}
                      placeholder="Enter the secret value"
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