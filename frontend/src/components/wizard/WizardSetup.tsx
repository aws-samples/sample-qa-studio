import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import AppLayout from "@cloudscape-design/components/app-layout";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import Container from "@cloudscape-design/components/container";
import FormField from "@cloudscape-design/components/form-field";
import Input from "@cloudscape-design/components/input";
import Textarea from "@cloudscape-design/components/textarea";
import Select from "@cloudscape-design/components/select";
import Alert from "@cloudscape-design/components/alert";
import Breadcrumb from '../common/Breadcrumb';
import { api } from '../../utils/api';
import { regionOptions } from '../../utils/browser_regions';

export default function WizardSetup() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [starting_url, setStartingUrl] = useState('');
  const [region, setRegion] = useState('us-east-1');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleStart = async () => {
    if (!name.trim() || !starting_url.trim()) {
      setError('Name and Starting URL are required');
      return;
    }

    setCreating(true);
    setError(null);

    try {
      const response = await api.post('wizard/start', {
        name: name.trim(),
        description: description.trim(),
        starting_url: starting_url.trim(),
        tags: [],
        region: region
      });

      // Validate response has required fields
      if (!response?.session_id || !response?.usecase_id) {
        throw new Error('Invalid response from server: missing session_id or usecase_id');
      }

      // Navigate to wizard with session info
      navigate(`/wizard/${response.session_id}`, {
        state: {
          sessionId: response.session_id,
          usecaseId: response.usecase_id
        }
      });
    } catch (err: any) {
      console.error('Wizard start error:', err);
      
      // Check if it's a 404 (endpoint not configured)
      if (err.status === 404 || err.message?.includes('404')) {
        setError('Wizard API endpoint not configured yet. Please configure the API Gateway routes first. See WIZARD_MODE_COMPLETE.md for instructions.');
      } else {
        setError(err.message || 'Failed to start wizard session. Check console for details.');
      }
      setCreating(false);
    }
  };

  const regions = regionOptions();

  return (
    <AppLayout
      navigationHide
      toolsHide
      content={
        <SpaceBetween direction="vertical" size="l">
          <Breadcrumb
            items={[
              { text: "Home", href: "/" },
              { text: "Create Use Case", href: "/create" },
              { text: "Interactive Wizard Setup" }
            ]}
          />

          <Header
            variant="h1"
            description="Configure your use case and start building interactively"
          >
            Interactive Wizard Setup
          </Header>

          {error && (
            <Alert
              type="error"
              dismissible
              onDismiss={() => setError(null)}
            >
              {error}
            </Alert>
          )}

          <Container>
            <SpaceBetween direction="vertical" size="l">
              <FormField
                label="Use Case Name"
                description="A descriptive name for your use case"
              >
                <Input
                  value={name}
                  onChange={({ detail }) => setName(detail.value)}
                  placeholder="e.g., Login Flow Test"
                />
              </FormField>

              <FormField
                label="Description"
                description="Optional description of what this use case tests"
              >
                <Textarea
                  value={description}
                  onChange={({ detail }) => setDescription(detail.value)}
                  placeholder="Describe what this use case does..."
                  rows={3}
                />
              </FormField>

              <FormField
                label="Starting URL"
                description="The URL where the test should begin"
              >
                <Input
                  value={starting_url}
                  onChange={({ detail }) => setStartingUrl(detail.value)}
                  placeholder="https://example.com"
                  type="url"
                />
              </FormField>

              <FormField
                label="Browser Region"
                description="AWS region where the browser will run"
              >
                <Select
                  selectedOption={regions.find(opt => opt.value === region) || null}
                  onChange={({ detail }) => setRegion(detail.selectedOption.value || 'us-east-1')}
                  options={regions}
                />
              </FormField>

              <SpaceBetween direction="horizontal" size="xs">
                <Button
                  variant="link"
                  onClick={() => navigate('/create')}
                  disabled={creating}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  onClick={handleStart}
                  loading={creating}
                  disabled={!name.trim() || !starting_url.trim()}
                >
                  Start Wizard
                </Button>
              </SpaceBetween>
            </SpaceBetween>
          </Container>
        </SpaceBetween>
      }
    />
  );
}
