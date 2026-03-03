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
  Multiselect,
  MultiselectProps
} from '@cloudscape-design/components';
import { userApi, CreateUserRequest } from '../utils/api';
import { ErrorState } from '../utils/errorManager';

const CreateUser: React.FC = () => {
  const navigate = useNavigate();
  const [createUserData, setCreateUserData] = useState<CreateUserRequest>({
    email: '',
    groups: []
  });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Available groups
  const groupOptions: MultiselectProps.Option[] = [
    {
      label: 'Users',
      value: 'users',
      description: 'Standard user permissions (read/write use cases, templates, executions)'
    },
    {
      label: 'Admins',
      value: 'admins',
      description: 'Full administrative access (all permissions + user management + OAuth clients)'
    }
  ];

  const [selectedGroups, setSelectedGroups] = useState<MultiselectProps.Option[]>([]);

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

          <FormField
            label="User Groups"
            description="Select which groups this user should belong to. Groups determine the user's permissions."
            errorText={selectedGroups.length === 0 ? 'At least one group must be selected' : undefined}
          >
            <Multiselect
              selectedOptions={selectedGroups}
              onChange={({ detail }) => {
                setSelectedGroups(detail.selectedOptions);
                setCreateUserData({
                  ...createUserData,
                  groups: detail.selectedOptions.map(opt => opt.value || '')
                });
              }}
              options={groupOptions}
              placeholder="Select groups (required)"
              disabled={creating}
              filteringType="auto"
              invalid={selectedGroups.length === 0}
            />
          </FormField>

          <Alert type="info">
            <SpaceBetween direction="vertical" size="xs">
              <div>
                <strong>Group Permissions:</strong>
              </div>
              <div>
                • <strong>Users:</strong> Can read/write use cases, templates, and executions
              </div>
              <div>
                • <strong>Admins:</strong> Full access including user management and OAuth client management
              </div>
              <div style={{ marginTop: '8px' }}>
                A secure temporary password will be automatically generated and sent to the user via welcome email.
                The user will be required to change this password on first login.
              </div>
            </SpaceBetween>
          </Alert>

          <SpaceBetween direction="horizontal" size="xs">
            <Button
              variant="primary"
              onClick={createUser}
              loading={creating}
              disabled={!createUserData.email || selectedGroups.length === 0 || creating}
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
