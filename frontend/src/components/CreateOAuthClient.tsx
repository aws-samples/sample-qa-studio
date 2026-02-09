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
  CopyToClipboard
} from '@cloudscape-design/components';
import { oauthClientApi, CreateOAuthClientRequest, CreateOAuthClientResponse } from '../utils/api';
import { ErrorState } from '../utils/errorManager';

const CreateOAuthClient: React.FC = () => {
  const navigate = useNavigate();
  const [clientData, setClientData] = useState<CreateOAuthClientRequest>({
    name: ''
  });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdClientId, setCreatedClientId] = useState("");
  const [createdClientSecret, setCreatedClientSecret] = useState("");
  const [createdAccessTokenValidity, setCreatedAccessTokenValidity] = useState(0);
  const [createdIdTokenValidity, setCreatedIdTokenValidity] = useState(0);
  const [createdRefreshTokenValidity, setCreatedRefreshTokenValidity] = useState(0);
  const [showSuccessModal, setShowSuccessModal] = useState(false);

  const createClient = async () => {
    setCreating(true);
    setError(null);
    
    try {
      const response = await oauthClientApi.create(clientData);
      console.log('OAuth client created:', response);
      console.log('Client ID:', response.client_id);
      console.log('Client Secret:', response.client_secret);
      setCreatedClientId(response.client_id)
      setCreatedClientSecret(response.client_secret)
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

  const handleCloseSuccessModal = () => {
    setShowSuccessModal(false);
    navigate('/oauth-clients');
  };

  const isFormValid = () => {
    return clientData.name.trim().length > 0;
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

          <Alert type="info">
            After creation, you will receive a Client ID and Client Secret. Make sure to save the Client Secret securely as it will only be shown once.
          </Alert>

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
