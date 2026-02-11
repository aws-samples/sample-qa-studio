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
  Modal,
  Box,
  CopyToClipboard,
  Multiselect,
  MultiselectProps
} from '@cloudscape-design/components';
import { oauthClientApi, CreateOAuthClientRequest } from '../utils/api';
import { ErrorState } from '../utils/errorManager';

// Available OAuth scopes with descriptions
const AVAILABLE_SCOPES: MultiselectProps.Option[] = [
  {
    label: 'api/usecases.read',
    value: 'api/usecases.read',
    description: 'Read use cases'
  },
  {
    label: 'api/usecases.write',
    value: 'api/usecases.write',
    description: 'Create, update, delete use cases'
  },
  {
    label: 'api/templates.read',
    value: 'api/templates.read',
    description: 'Read templates'
  },
  {
    label: 'api/templates.write',
    value: 'api/templates.write',
    description: 'Create, update, delete templates'
  },
  {
    label: 'api/executions.read',
    value: 'api/executions.read',
    description: 'View execution results'
  },
  {
    label: 'api/executions.write',
    value: 'api/executions.write',
    description: 'Modify execution records'
  },
  {
    label: 'api/usecases.execute',
    value: 'api/usecases.execute',
    description: 'Trigger use case executions'
  },
  {
    label: 'api/oauth-clients.read',
    value: 'api/oauth-clients.read',
    description: 'Read OAuth clients'
  },
  {
    label: 'api/oauth-clients.write',
    value: 'api/oauth-clients.write',
    description: 'Create, update, delete OAuth clients'
  },
  {
    label: 'api/admin',
    value: 'api/admin',
    description: 'Full administrative access'
  }
];

const CreateOAuthClient: React.FC = () => {
  const navigate = useNavigate();
  const [clientData, setClientData] = useState<CreateOAuthClientRequest>({
    name: '',
    scopes: [] // No default scopes
  });
  const [selectedScopes, setSelectedScopes] = useState<MultiselectProps.Option[]>([]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdClientId, setCreatedClientId] = useState("");
  const [createdClientSecret, setCreatedClientSecret] = useState("");
  const [createdScopes, setCreatedScopes] = useState<string[]>([]);
  const [createdAccessTokenValidity, setCreatedAccessTokenValidity] = useState(0);
  const [createdIdTokenValidity, setCreatedIdTokenValidity] = useState(0);
  const [createdRefreshTokenValidity, setCreatedRefreshTokenValidity] = useState(0);
  const [showSuccessModal, setShowSuccessModal] = useState(false);

  const createClient = async () => {
    setCreating(true);
    setError(null);
    
    try {
      const response = await oauthClientApi.create(clientData);
      setCreatedClientId(response.client_id)
      setCreatedClientSecret(response.client_secret)
      setCreatedScopes(response.scopes || [])
      setCreatedAccessTokenValidity(response?.access_token_validity || 0)
      setCreatedIdTokenValidity(response?.id_token_validity || 0)
      setCreatedRefreshTokenValidity(response?.refresh_token_validity || 0)
      setShowSuccessModal(true);
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to create OAuth client');
    } finally {
      setCreating(false);
    }
  };

  const handleScopeChange = (detail: MultiselectProps.MultiselectChangeDetail) => {
    setSelectedScopes(detail.selectedOptions);
    setClientData({
      ...clientData,
      scopes: detail.selectedOptions.map(opt => opt.value || '')
    });
  };

  const isFormValid = () => {
    return clientData.name.trim().length > 0 && (clientData.scopes?.length || 0) > 0;
  };

  const handleCloseSuccessModal = () => {
    setShowSuccessModal(false);
    navigate('/oauth-clients');
  };

  return (
    <SpaceBetween direction="vertical" size="l">
      <BreadcrumbGroup
        items={[
          { text: 'OAuth Clients', href: '/oauth-clients' },
          { text: 'Create Client', href: '/oauth-clients/create' }
        ]}
        onFollow={(event) => {
          event.preventDefault();
          navigate(event.detail.href);
        }}
      />

      <Header
        variant="h1"
        description="Create a new OAuth 2.0 client for application authentication and authorization."
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
            description="A unique name to identify this OAuth client."
            constraintText="Required"
          >
            <Input
              value={clientData.name}
              onChange={({ detail }) =>
                setClientData({ ...clientData, name: detail.value })
              }
              placeholder="My Application"
              disabled={creating}
            />
          </FormField>

          <FormField
            label="Scopes"
            description="Select the permissions this OAuth client will have."
            constraintText="At least one scope is required"
          >
            <Multiselect
              selectedOptions={selectedScopes}
              onChange={({ detail }) => handleScopeChange(detail)}
              options={AVAILABLE_SCOPES}
              placeholder="Select scopes"
              disabled={creating}
              filteringType="auto"
            />
          </FormField>

          <SpaceBetween direction="horizontal" size="xs">
            <Button
              variant="primary"
              onClick={createClient}
              loading={creating}
              disabled={!isFormValid() || creating}
            >
              Create Client
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

      {/* Success Modal with Client Secret */}
      <Modal
        onDismiss={handleCloseSuccessModal}
        visible={showSuccessModal}
        closeAriaLabel="Close modal"
        size="medium"
        footer={
          <Box float="right">
            <Button variant="primary" onClick={handleCloseSuccessModal}>
              Done
            </Button>
          </Box>
        }
        header="OAuth Client Created Successfully"
      >
        <SpaceBetween direction="vertical" size="l">
          <Alert type="warning">
            Make sure to copy the Client Secret now. You won't be able to see it again!
          </Alert>

          <FormField label="Client ID">
            <CopyToClipboard
              textToCopy={createdClientId}
              textToDisplay={createdClientId}
              copySuccessText="Copied!"
              copyErrorText="Failed to copy"
              variant="inline"
            />
          </FormField>

          <FormField label="Client Secret">
            <CopyToClipboard
              textToCopy={createdClientSecret}
              textToDisplay={createdClientSecret}
              copySuccessText="Copied!"
              copyErrorText="Failed to copy"
              variant="inline"
            />
          </FormField>

          <FormField label="Scopes">
            <Box variant="p">
              {createdScopes.map((scope, index) => (
                <Box key={index} variant="code">{scope}</Box>
              ))}
            </Box>
          </FormField>

          <Box variant="p">
            <strong>Token Validity:</strong>
            <ul>
              <li>Access Token: {createdAccessTokenValidity} minutes</li>
              <li>ID Token: {createdIdTokenValidity} minutes</li>
              <li>Refresh Token: {createdRefreshTokenValidity} days</li>
            </ul>
          </Box>
        </SpaceBetween>
      </Modal>
    </SpaceBetween>
  );
};

export default CreateOAuthClient;
