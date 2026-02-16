import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Container,
  Header,
  SpaceBetween,
  Button,
  FormField,
  Input,
  Textarea,
  Alert,
  BreadcrumbGroup,
  Multiselect,
  MultiselectProps
} from '@cloudscape-design/components';
import { testSuites, CreateTestSuiteRequest } from '../utils/api';
import { ErrorState } from '../utils/errorManager';

const CreateTestSuite: React.FC = () => {
  const navigate = useNavigate();
  const [suiteData, setSuiteData] = useState<CreateTestSuiteRequest>({
    name: '',
    description: '',
    tags: []
  });
  const [selectedTags, setSelectedTags] = useState<MultiselectProps.Option[]>([]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<{
    name?: string;
  }>({});

  const validateName = (name: string): string | undefined => {
    if (name.length === 0) {
      return 'Name is required';
    }
    if (name.length < 3) {
      return 'Name must be at least 3 characters';
    }
    if (name.length > 100) {
      return 'Name must not exceed 100 characters';
    }
    return undefined;
  };

  const handleNameChange = (value: string) => {
    setSuiteData({ ...suiteData, name: value });
    const error = validateName(value);
    setValidationErrors({ ...validationErrors, name: error });
  };

  const handleTagChange = (detail: MultiselectProps.MultiselectChangeDetail) => {
    setSelectedTags([...detail.selectedOptions]);
    setSuiteData({
      ...suiteData,
      tags: detail.selectedOptions.map(opt => opt.value || '')
    });
  };

  const isFormValid = (): boolean => {
    const nameError = validateName(suiteData.name);
    return !nameError;
  };

  const createSuite = async () => {
    // Final validation
    const nameError = validateName(suiteData.name);
    
    if (nameError) {
      setValidationErrors({ name: nameError });
      return;
    }

    setCreating(true);
    setError(null);
    
    try {
      const response = await testSuites.create(suiteData);
      // Navigate to the newly created suite detail page
      navigate(`/test-suites/${response.id}`);
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to create test suite');
    } finally {
      setCreating(false);
    }
  };

  // Common tag suggestions
  const tagSuggestions: MultiselectProps.Option[] = [
    { label: 'smoke', value: 'smoke' },
    { label: 'regression', value: 'regression' },
    { label: 'integration', value: 'integration' },
    { label: 'e2e', value: 'e2e' },
    { label: 'critical', value: 'critical' },
    { label: 'nightly', value: 'nightly' }
  ];

  return (
    <SpaceBetween direction="vertical" size="l">
      <BreadcrumbGroup
        items={[
          { text: 'Test Suites', href: '/test-suites' },
          { text: 'Create Test Suite', href: '/test-suites/create' }
        ]}
        onFollow={(event) => {
          event.preventDefault();
          navigate(event.detail.href);
        }}
      />

      <Header
        variant="h1"
        description="Create a new test suite to group and execute multiple use cases together."
      >
        Create Test Suite
      </Header>

      {error && (
        <Alert type="error" dismissible onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Container>
        <SpaceBetween direction="vertical" size="l">
          <FormField
            label="Name"
            description="A descriptive name for this test suite."
            constraintText="Required. 3-100 characters."
            errorText={validationErrors.name}
          >
            <Input
              value={suiteData.name}
              onChange={({ detail }) => handleNameChange(detail.value)}
              placeholder="Smoke Tests"
              disabled={creating}
              invalid={!!validationErrors.name}
            />
          </FormField>

          <FormField
            label="Description"
            description="Describe the purpose of this test suite."
          >
            <Textarea
              value={suiteData.description}
              onChange={({ detail }) =>
                setSuiteData({ ...suiteData, description: detail.value })
              }
              placeholder="Critical path tests that run before each release"
              disabled={creating}
              rows={3}
            />
          </FormField>

          <FormField
            label="Tags"
            description="Add tags to categorize and filter test suites."
          >
            <Multiselect
              selectedOptions={selectedTags}
              onChange={({ detail }) => handleTagChange(detail)}
              options={tagSuggestions}
              placeholder="Select or type custom tags"
              disabled={creating}
              filteringType="auto"
              tokenLimit={5}
            />
          </FormField>

          <SpaceBetween direction="horizontal" size="xs">
            <Button
              variant="primary"
              onClick={createSuite}
              loading={creating}
              disabled={!isFormValid() || creating}
            >
              Create Test Suite
            </Button>
            <Button
              onClick={() => navigate('/test-suites')}
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

export default CreateTestSuite;
