import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Container,
  Header,
  SpaceBetween,
  Button,
  Table,
  Box,
  Modal,
  Alert,
  StatusIndicator,
  CopyToClipboard,
  FormField
} from '@cloudscape-design/components';
import { oauthClientApi, OAuthClient } from '../utils/api';
import { ErrorState } from '../utils/errorManager';

const OAuthClients: React.FC = () => {
  const [clients, setClients] = useState<OAuthClient[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showRotateModal, setShowRotateModal] = useState(false);
  const [showRotateSuccessModal, setShowRotateSuccessModal] = useState(false);
  const [clientToDelete, setClientToDelete] = useState<OAuthClient | null>(null);
  const [clientToRotate, setClientToRotate] = useState<OAuthClient | null>(null);
  const [rotatedClientId, setRotatedClientId] = useState<string>('');
  const [rotatedClientSecret, setRotatedClientSecret] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [sortingColumn, setSortingColumn] = useState<any>({ sortingField: 'created_date' });
  const [sortingDescending, setSortingDescending] = useState(true);

  const navigate = useNavigate();

  const fetchClients = async () => {
    try {
      setLoading(true);
      const data = await oauthClientApi.list();
      setClients(data.clients || []);
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to fetch OAuth clients');
    } finally {
      setLoading(false);
    }
  };

  const deleteClient = async () => {
    if (!clientToDelete) return;

    try {
      setDeleting(true);
      await oauthClientApi.delete(clientToDelete.client_id);
      setSuccess('OAuth client deleted successfully');
      setClientToDelete(null);
      setShowDeleteModal(false);
      fetchClients();
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to delete OAuth client');
    } finally {
      setDeleting(false);
    }
  };

  const rotateSecret = async () => {
    if (!clientToRotate) return;

    try {
      setRotating(true);
      const response = await oauthClientApi.rotateSecret(clientToRotate.client_id);
      setRotatedClientId(response.client_id);
      setRotatedClientSecret(response.client_secret);
      setShowRotateModal(false);
      setShowRotateSuccessModal(true);
      fetchClients();
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to rotate OAuth client secret');
    } finally {
      setRotating(false);
    }
  };

  const handleCloseRotateSuccessModal = () => {
    setShowRotateSuccessModal(false);
    setClientToRotate(null);
    setRotatedClientId('');
    setRotatedClientSecret('');
  };

  const getStatusIndicator = (enabled: boolean) => {
    return enabled ? (
      <StatusIndicator type="success">Enabled</StatusIndicator>
    ) : (
      <StatusIndicator type="stopped">Disabled</StatusIndicator>
    );
  };

  useEffect(() => {
    fetchClients();
  }, []);

  useEffect(() => {
    if (error || success) {
      const timer = setTimeout(() => {
        setError(null);
        setSuccess(null);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [error, success]);

  return (
    <SpaceBetween direction="vertical" size="l">
      <Header
        variant="h1"
        description="Manage OAuth 2.0 clients for application authentication."
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            <Button
              onClick={fetchClients}
              iconName="refresh"
              variant="icon"
            />
            <Button
              variant="primary"
              onClick={() => navigate('/oauth-clients/create')}
            >
              Create OAuth Client
            </Button>
          </SpaceBetween>
        }
      >
        OAuth Client Management
      </Header>

      {error && (
        <Alert type="error" dismissible onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert type="success" dismissible onDismiss={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      <Container>
        <Table
          variant="embedded"
          sortingColumn={sortingColumn}
          sortingDescending={sortingDescending}
          onSortingChange={(event) => {
            setSortingColumn(event.detail.sortingColumn);
            setSortingDescending(event.detail.isDescending || false);
          }}
          columnDefinitions={[
            {
              id: 'client_name',
              header: 'Client Name',
              cell: (client: OAuthClient) => client.client_name,
              sortingField: 'client_name'
            },
            {
              id: 'client_id',
              header: 'Client ID',
              cell: (client: OAuthClient) => (
                <code style={{ fontSize: '0.875rem' }}>
                  {client.client_id}
                </code>
              )
            },
            {
              id: 'status',
              header: 'Status',
              cell: (client: OAuthClient) => getStatusIndicator(client.enabled)
            },
            {
              id: 'created_date',
              header: 'Created',
              cell: (client: OAuthClient) => new Date(client.created_date).toLocaleDateString(),
              sortingField: 'created_date'
            },
            {
              id: 'created_by',
              header: 'Created By',
              cell: (client: OAuthClient) => client.created_by || 'System',
              sortingField: 'created_by'
            },
            {
              id: 'actions',
              header: 'Actions',
              cell: (client: OAuthClient) => (
                client.created_by ? (
                  <SpaceBetween direction="horizontal" size="xs">
                    <Button
                      variant="icon"
                      iconName="refresh"
                      onClick={() => {
                        setClientToRotate(client);
                        setShowRotateModal(true);
                      }}
                      ariaLabel={`Rotate secret for ${client.client_name}`}
                    />
                    <Button
                      variant="icon"
                      iconName="remove"
                      onClick={() => {
                        setClientToDelete(client);
                        setShowDeleteModal(true);
                      }}
                      ariaLabel={`Delete ${client.client_name}`}
                    />
                  </SpaceBetween>
                ) : (
                  <Box color="text-status-inactive">
                    -
                  </Box>
                )
              )
            }
          ]}
          items={clients}
          loading={loading}
          loadingText="Loading OAuth clients..."
          empty={
            <Box textAlign="center" color="inherit">
              <b>No OAuth clients found</b>
              <Box padding={{ bottom: 's' }} variant="p" color="inherit">
                No OAuth clients to display.
              </Box>
              <Button onClick={() => navigate('/oauth-clients/create')}>
                Create OAuth Client
              </Button>
            </Box>
          }
        />
      </Container>

      {/* Delete Confirmation Modal */}
      <Modal
        onDismiss={() => !deleting && setShowDeleteModal(false)}
        visible={showDeleteModal}
        closeAriaLabel="Close modal"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button 
                variant="link" 
                onClick={() => setShowDeleteModal(false)}
                disabled={deleting}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={deleteClient}
                loading={deleting}
                disabled={deleting}
              >
                Delete
              </Button>
            </SpaceBetween>
          </Box>
        }
        header="Delete OAuth Client"
      >
        <Box variant="span">
          Are you sure you want to delete the OAuth client{' '}
          <Box variant="span" fontWeight="bold">
            {clientToDelete?.client_name}
          </Box>
          ? This action cannot be undone and will revoke access for all applications using this client.
        </Box>
      </Modal>

      {/* Rotate Secret Confirmation Modal */}
      <Modal
        onDismiss={() => !rotating && setShowRotateModal(false)}
        visible={showRotateModal}
        closeAriaLabel="Close modal"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button 
                variant="link" 
                onClick={() => setShowRotateModal(false)}
                disabled={rotating}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={rotateSecret}
                loading={rotating}
                disabled={rotating}
              >
                Rotate Secret
              </Button>
            </SpaceBetween>
          </Box>
        }
        header="Rotate OAuth Client Secret"
      >
        <SpaceBetween direction="vertical" size="m">
          <Alert type="warning">
            This will immediately invalidate the old client secret. Any applications using the old credentials will stop working.
          </Alert>
          <Box variant="span">
            Are you sure you want to rotate the secret for OAuth client{' '}
            <Box variant="span" fontWeight="bold">
              {clientToRotate?.client_name}
            </Box>
            ?
          </Box>
        </SpaceBetween>
      </Modal>

      {/* Rotate Secret Success Modal */}
      <Modal
        onDismiss={handleCloseRotateSuccessModal}
        visible={showRotateSuccessModal}
        closeAriaLabel="Close modal"
        size="medium"
        footer={
          <Box float="right">
            <Button variant="primary" onClick={handleCloseRotateSuccessModal}>
              Done
            </Button>
          </Box>
        }
        header="OAuth Client Secret Rotated Successfully"
      >
        <SpaceBetween direction="vertical" size="l">
          <Alert type="warning">
            Make sure to copy the new Client Secret now. You won't be able to see it again!
          </Alert>

          <FormField label="Client ID">
            <CopyToClipboard
              textToCopy={rotatedClientId}
              textToDisplay={rotatedClientId}
              copySuccessText="Copied!"
              copyErrorText="Failed to copy"
              variant="inline"
            />
          </FormField>

          <FormField label="New Client Secret">
            <CopyToClipboard
              textToCopy={rotatedClientSecret}
              textToDisplay={rotatedClientSecret}
              copySuccessText="Copied!"
              copyErrorText="Failed to copy"
              variant="inline"
            />
          </FormField>

          <Box variant="p" color="text-status-info">
            The old client secret has been invalidated. Update your applications with the new credentials immediately.
          </Box>
        </SpaceBetween>
      </Modal>
    </SpaceBetween>
  );
};

export default OAuthClients;
