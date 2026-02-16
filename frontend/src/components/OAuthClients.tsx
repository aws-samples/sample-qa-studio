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
  StatusIndicator
} from '@cloudscape-design/components';
import { oauthClientApi, OAuthClient } from '../utils/api';
import { ErrorState } from '../utils/errorManager';

const OAuthClients: React.FC = () => {
  const [clients, setClients] = useState<OAuthClient[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [clientToDelete, setClientToDelete] = useState<OAuthClient | null>(null);
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
                  <Button
                    variant="icon"
                    iconName="remove"
                    onClick={() => {
                      setClientToDelete(client);
                      setShowDeleteModal(true);
                    }}
                    ariaLabel={`Delete ${client.client_name}`}
                  />
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
    </SpaceBetween>
  );
};

export default OAuthClients;
