import React, { useState, useEffect } from 'react';
import {
  Container,
  Header,
  SpaceBetween,
  Button,
  Table,
  Box,
  Modal,
  FormField,
  Input,
  Alert,
  StatusIndicator
} from '@cloudscape-design/components';
import { userApi, User, CreateUserRequest } from '../utils/api';
import { ErrorState } from '../utils/errorManager';

const Users: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [userToDelete, setUserToDelete] = useState<User | null>(null);
  const [createUserData, setCreateUserData] = useState<CreateUserRequest>({
    email: ''
  });
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const data = await userApi.list();
      setUsers(data.users || []);
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to fetch users');
    } finally {
      setLoading(false);
    }
  };

  const createUser = async () => {
    try {
      await userApi.create(createUserData);
      setSuccess('User created successfully with auto-generated password. Welcome email sent.');
      setShowCreateModal(false);
      setCreateUserData({
        email: ''
      });
      fetchUsers();
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to create user');
    }
  };

  const deleteUser = async () => {
    if (!userToDelete) return;

    try {
      await userApi.delete(userToDelete.username);
      setSuccess('User deleted successfully');
      setUserToDelete(null);
      setShowDeleteModal(false);
      fetchUsers();
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to delete user');
    }
  };

  const getStatusIndicator = (status: string, enabled: boolean) => {
    if (!enabled) {
      return <StatusIndicator type="stopped">Disabled</StatusIndicator>;
    }

    switch (status) {
      case 'CONFIRMED':
        return <StatusIndicator type="success">Active</StatusIndicator>;
      case 'UNCONFIRMED':
        return <StatusIndicator type="pending">Unconfirmed</StatusIndicator>;
      case 'FORCE_CHANGE_PASSWORD':
        return <StatusIndicator type="warning">Password Change Required</StatusIndicator>;
      default:
        return <StatusIndicator type="info">{status}</StatusIndicator>;
    }
  };

  useEffect(() => {
    fetchUsers();
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
              onClick={fetchUsers}
              iconName="refresh"
              variant="icon"
            />
            <Button
              variant="primary"
              onClick={() => setShowCreateModal(true)}
            >
              Create User
            </Button>
          </SpaceBetween>
        }
      >
        User Management
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
              id: 'email',
              header: 'Email',
              cell: (user: User) => user.email,
              sortingField: 'email'
            },
            {
              id: 'status',
              header: 'Status',
              cell: (user: User) => getStatusIndicator(user.status, user.enabled)
            },
            {
              id: 'created_at',
              header: 'Created',
              cell: (user: User) => new Date(user.created_at).toLocaleDateString(),
              sortingField: 'created_at'
            },
            {
              id: 'actions',
              header: 'Actions',
              cell: (user: User) => (
                <Button
                  variant="link"
                  onClick={() => {
                    setUserToDelete(user);
                    setShowDeleteModal(true);
                  }}
                >
                  Delete
                </Button>
              )
            }
          ]}
          items={users}
          loading={loading}
          loadingText="Loading users..."
          empty={
            <Box textAlign="center" color="inherit">
              <b>No users found</b>
              <Box padding={{ bottom: 's' }} variant="p" color="inherit">
                No users to display.
              </Box>
              <Button onClick={() => setShowCreateModal(true)}>Create User</Button>
            </Box>
          }
        />
      </Container>

      {/* Create User Modal */}
      <Modal
          onDismiss={() => setShowCreateModal(false)}
          visible={showCreateModal}
          closeAriaLabel="Close modal"
          footer={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="xs">
                <Button variant="link" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  onClick={createUser}
                  disabled={!createUserData.email}
                >
                  Create User
                </Button>
              </SpaceBetween>
            </Box>
          }
          header="Create New User"
        >
          <SpaceBetween size="m">
            <FormField
              label="Email Address"
              description="The user's email address. A temporary password will be auto-generated and sent via welcome email."
            >
              <Input
                value={createUserData.email}
                onChange={({ detail }) =>
                  setCreateUserData({ ...createUserData, email: detail.value })
                }
                placeholder="user@example.com"
                type="email"
              />
            </FormField>

            <Alert type="info">
              A secure temporary password will be automatically generated and sent to the user via welcome email.
              The user will be required to change this password on first login.
            </Alert>
          </SpaceBetween>
        </Modal>

        {/* Delete Confirmation Modal */}
        <Modal
          onDismiss={() => setShowDeleteModal(false)}
          visible={showDeleteModal}
          closeAriaLabel="Close modal"
          footer={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="xs">
                <Button variant="link" onClick={() => setShowDeleteModal(false)}>
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  onClick={deleteUser}
                >
                  Delete
                </Button>
              </SpaceBetween>
            </Box>
          }
          header="Delete User"
        >
          <Box variant="span">
            Are you sure you want to delete{' '}
            <Box variant="span" fontWeight="bold">
              {userToDelete?.email}
            </Box>
            ? This action cannot be undone.
          </Box>
        </Modal>
    </SpaceBetween>
  );
};

export default Users;