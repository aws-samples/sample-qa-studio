import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
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
import { testSuites, UpdateTestSuiteRequest } from '../utils/api';
import { ErrorState } from '../utils/errorManager';
import { ContainerLoading } from './common/LoadingStates';

const UpdateTestSuite: React.FC = () => {
  const navigate = useNavigate();
  const { id: paramId } = useParams<{ id: string }>();
  const [id, setId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [suiteData, setSuiteData] = useState<UpdateTestSuiteRequest>({
    name: '',
    description: '',
    tags: []
  });
  const [selectedTags, setSelectedTags] = useState<MultiselectProps.Option[]>([]);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<{
    name?: string;
  }>({});

  // Redirect if no ID
  useEffect(() => {
    if (!paramId) {
      navigate('/test-suites');
    } else {
      setId(paramId);
    }
  }, [paramId, navigate]);

  // Fetch existing suite data
  useEffect(() => {
    if (!id) return;
    
    const fetchSuite = async () => {
      try {
        setLoading(true);
        const suite = await testSuites.get(id!);
        setSuiteData({
          name: suite.name,
          description: suite.description || '',
          tags: suite.tags || []
        });
        setSelectedTags((suite.tags || []).map(tag => ({ label: tag, value: tag })));
      } catch (err) {
        const errorState = err as ErrorState;
        setError(errorState.message || 'Failed to fetch test suite');
      } finally {
        setLoading(false);
      }
    };

    fetchSuite();
  }, [id]);

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

  const updateSuite = async () => {
    if (!id) return;
    
    const nameError = validateName(suiteData.name);
    
    if (nameError) {
      setValidationErrors({ name: nameError });
      return;
    }

    setUpdating(true);
    setError(null);
    
    try {
      await testSuites.update(id!, suiteData);
      navigate(`/test-suites/${id}`);
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to update test suite');
    } finally {
      setUpdating(false);
    }
  };

  const tagSuggestions: MultiselectProps.Option[] = [
    { label: 'smoke', value: 'smoke' },
    { label: 'regression', value: 'regression' },
    { label: 'integration', value: 'integration' },
    { label: 'e2e', value: 'e2e' },
    { label: 'critical', value: 'critical' },
    { label: 'nightly', value: 'nightly' }
  ];

  if (loading) {
    return (
      <SpaceBetween direction="vertical" size="l">
        <BreadcrumbGroup
          items={[
            { text: 'Test Suites', href: '/test-suites' },
            { text: 'Loading...', href: '#' }
          ]}
          onFollow={(event) => {
            event.preventDefault();
            if (event.detail.href !== '#') {
              navigate(event.detail.href);
            }
          }}
        />
        <ContainerLoading title="Edit Test Suite" text="Loading test suite..." />
      </SpaceBetween>
    );
  }

  if (!id) {
    return null;
  }

  return (
    <SpaceBetween direction="vertical" size="l">
      <BreadcrumbGroup
        items={[
          { text: 'Test Suites', href: '/test-suites' },
          { text: suiteData.name, href: `/test-suites/${id!}` },
          { text: 'Edit', href: `/test-suites/${id!}/edit` }
        ]}
        onFollow={(event) => {
          event.preventDefault();
          navigate(event.detail.href);
        }}
      />

      <Header
        variant="h1"
        description="Update test suite details."
      >
        Edit Test Suite
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
              disabled={updating}
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
              disabled={updating}
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
              disabled={updating}
              filteringType="auto"
              tokenLimit={5}
            />
          </FormField>

          <SpaceBetween direction="horizontal" size="xs">
            <Button
              variant="primary"
              onClick={updateSuite}
              loading={updating}
              disabled={!isFormValid() || updating}
            >
              Save Changes
            </Button>
            <Button
              onClick={() => navigate(`/test-suites/${id!}`)}
              disabled={updating}
            >
              Cancel
            </Button>
          </SpaceBetween>
        </SpaceBetween>
      </Container>
    </SpaceBetween>
  );
};

export default UpdateTestSuite;
