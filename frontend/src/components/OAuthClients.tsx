import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Container,
  Header,
  SpaceBetween,
  Button,
  Table,
  Box,
  Alert
} from '@cloudscape-design/components';

const OAuthClients: React.FC = () => {
  const [clients, setClients] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const navigate = useNavigate();

  const fetchClients = async () => {
    try {
      setLoading(true);
      // TODO: Implement API call to fetch OAuth clients
      setClients([]);
    } catch (err) {
      setError('Failed to fetch OAuth clients');
    } finally {
      setLoading(false);
    }
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
        OAuth Clients
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
          columnDefinitions={[
            {
              id: 'clientId',
              header: 'Client ID',
              cell: (client: any) => client.clientId || '-',
              sortingField: 'clientId'
            },
            {
              id: 'clientName',
              header: 'Client Name',
              cell: (client: any) => client.clientName || '-',
              sortingField: 'clientName'
            },
            {
              id: 'createdAt',
              header: 'Created',
              cell: (client: any) => client.createdAt ? new Date(client.createdAt).toLocaleDateString() : '-',
              sortingField: 'createdAt'
            },
            {
              id: 'actions',
              header: 'Actions',
              cell: (client: any) => (
                <SpaceBetween direction="horizontal" size="xs">
                  <Button variant="link">View</Button>
                  <Button variant="link">Delete</Button>
                </SpaceBetween>
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
                Create an OAuth client to enable CI/CD pipelines to interact with the application.
              </Box>
              <Button variant="primary" onClick={() => navigate('/oauth-clients/create')}>Create OAuth Client</Button>
            </Box>
          }
        />
      </Container>
    </SpaceBetween>
  );
};

export default OAuthClients;
