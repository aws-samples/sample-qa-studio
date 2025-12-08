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
  BreadcrumbGroup
} from '@cloudscape-design/components';
import { userApi, CreateUserRequest } from '../utils/api';
import { ErrorState } from '../utils/errorManager';

const CreateUser: React.FC = () => {
  const navigate = useNavigate();
  const [createUserData, setCreateUserData] = useState<CreateUserRequest>({
    email: ''
  });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createUser = async () => {
    setCreating(true);
    setError(null);
    
    try {
      await userApi.create(createUserData);
      navigate('/users');
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to create user');
    } finally {
      setCreating(false);
    }
  };

  return (
    <SpaceBetween direction="vertical" size="l">
      <BreadcrumbGroup
        items={[
          { text: 'Users', href: '/users' },
          { text: 'Create User', href: '/users/create' }
        ]}
        onFollow={(event) => {
          event.preventDefault();
          navigate(event.detail.href);
        }}
      />

      <Header
        variant="h1"
        description="Create a new user account. A temporary password will be auto-generated and sent via welcome email."
      >
        Create New User
      </Header>

      {error && (
        <Alert type="error" dismissible onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Container>
        <SpaceBetween direction="vertical" size="l">
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
              disabled={creating}
            />
          </FormField>

          <Alert type="info">
            A secure temporary password will be automatically generated and sent to the user via welcome email.
            The user will be required to change this password on first login.
          </Alert>

          <SpaceBetween direction="horizontal" size="xs">
            <Button
              variant="primary"
              onClick={createUser}
              loading={creating}
              disabled={!createUserData.email || creating}
            >
              Create
            </Button>
            <Button
              onClick={() => navigate('/users')}
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

export default CreateUser;
