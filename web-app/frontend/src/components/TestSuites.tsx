import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Container,
  Header,
  SpaceBetween,
  Button,
  Box,
  Alert
} from '@cloudscape-design/components';
import { testSuites, TestSuite } from '../utils/api';
import { ErrorState } from '../utils/errorManager';
import { TestSuitesTable } from './common/TestSuitesTable';

const TestSuites: React.FC = () => {
  const [suites, setSuites] = useState<TestSuite[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const navigate = useNavigate();

  const fetchSuites = async () => {
    try {
      setLoading(true);
      const data = await testSuites.list();
      setSuites(data.suites || []);
    } catch (err) {
      const errorState = err as ErrorState;
      setError(errorState.message || 'Failed to fetch test suites');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSuites();
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
        description="Manage and execute test suites to run multiple use cases together."
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            <Button
              onClick={fetchSuites}
              iconName="refresh"
              variant="icon"
            />
            <Button
              variant="primary"
              onClick={() => navigate('/test-suites/create')}
            >
              Create Test Suite
            </Button>
          </SpaceBetween>
        }
      >
        Test Suites
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
        <TestSuitesTable
          items={suites}
          loading={loading}
          empty={
            <Box textAlign="center" color="inherit">
              <b>No test suites found</b>
              <Box padding={{ bottom: 's' }} variant="p" color="inherit">
                No test suites to display.
              </Box>
              <Button onClick={() => navigate('/test-suites/create')}>
                Create Test Suite
              </Button>
            </Box>
          }
        />
      </Container>
    </SpaceBetween>
  );
};

export default TestSuites;
