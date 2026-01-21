import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Container,
  Header,
  SpaceBetween,
  Button,
  FormField,
  Input,
  Alert,
  BreadcrumbGroup,
  Textarea
} from '@cloudscape-design/components';

interface CreateOAuthClientRequest {
  clientName: string;
  description: string;
}

const CreateOAuthClient: React.FC = () => {
  const navigate = useNavigate();
  const [clientData, setClientData] = useState<CreateOAuthClientRequest>({
    clientName: '',
    description: ''
  });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createClient = async () => {
    setCreating(true);
    setError(null);
    
    try {
      // TODO: Implement API call to create OAuth client in Cognito
      // await oauthClientApi.create(clientData);
      
      // For now, simulate success
      setTimeout(() => {
        navigate('/oauth-clients');
      }, 1000);
    } catch (err) {
      setError('Failed to create OAuth client');
    } finally {
      setCreating(false);
    }
  };

  return (
    <SpaceBetween direction="vertical" size="l">
      <BreadcrumbGroup
        items={[
          { text: 'OAuth Clients', href: '/oauth-clients' },
          { text: 'Create OAuth Client', href: '/oauth-clients/create' }
        ]}
        onFollow={(event) => {
          event.preventDefault();
          navigate(event.detail.href);
        }}
      />

      <Header
        variant="h1"
        description="Create a new OAuth client for CI/CD pipelines and automated integrations."
      >
        Create OAuth Client
      </Header>

      {error && (
        <Alert type="error" dismissible onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Container>
        <SpaceBetween direction="vertical" size="l">
          <FormField
            label="Client Name"
            description="A descriptive name for this OAuth client (e.g., 'CI/CD Pipeline', 'Jenkins Integration')."
          >
            <Input
              value={clientData.clientName}
              onChange={({ detail }) =>
                setClientData({ ...clientData, clientName: detail.value })
              }
              placeholder="My CI/CD Pipeline"
              disabled={creating}
            />
          </FormField>

          <FormField
            label="Description"
            description="Optional description to help identify the purpose of this client."
          >
            <Textarea
              value={clientData.description}
              onChange={({ detail }) =>
                setClientData({ ...clientData, description: detail.value })
              }
              placeholder="OAuth client for automated testing and deployment"
              disabled={creating}
              rows={3}
            />
          </FormField>

          <Alert type="info">
            After creating the OAuth client, you will receive a Client ID and Client Secret. 
            Make sure to save the Client Secret securely as it will only be shown once.
          </Alert>

          <SpaceBetween direction="horizontal" size="xs">
            <Button
              variant="primary"
              onClick={createClient}
              loading={creating}
              disabled={!clientData.clientName || creating}
            >
              Create
            </Button>
            <Button
              onClick={() => navigate('/oauth-clients')}
              disabled={creating}
            >
              Cancel
            </Button>
          </SpaceBetween>
        </SpaceBetween>
      </Container>
    </SpaceBetween>
  );
};

export default CreateOAuthClient;
