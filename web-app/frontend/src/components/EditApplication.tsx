import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Box from '@cloudscape-design/components/box';
import Button from '@cloudscape-design/components/button';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import FormField from '@cloudscape-design/components/form-field';
import Input from '@cloudscape-design/components/input';
import Textarea from '@cloudscape-design/components/textarea';
import TokenGroup from '@cloudscape-design/components/token-group';
import Alert from '@cloudscape-design/components/alert';
import Spinner from '@cloudscape-design/components/spinner';
import BreadcrumbGroup from '@cloudscape-design/components/breadcrumb-group';
import { api } from '../utils/api';
import { Application } from '../types/application';

export default function EditApplication() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState('');
  const [name, setName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [description, setDescription] = useState('');
  const [team, setTeam] = useState('');
  const [environments, setEnvironments] = useState<string[]>([]);
  const [envInput, setEnvInput] = useState('');

  useEffect(() => {
    loadApplication();
  }, [id]);

  async function loadApplication() {
    if (!id) return;
    setLoading(true);
    try {
      const app: Application = await api.get(`applications/${id}`);
      setName(app.name);
      setBaseUrl(app.base_url);
      setDescription(app.description || '');
      setTeam(app.team || '');
      setEnvironments(app.environments || []);
    } catch (e: any) {
      setError(e.message || 'Failed to load application');
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    if (!name.trim()) { setError('Name is required'); return; }
    if (!baseUrl.trim()) { setError('Base URL is required'); return; }

    setSaving(true);
    setError('');
    try {
      await api.patch(`applications/${id}`, { name, base_url: baseUrl, description, team, environments });
      navigate(`/applications/${id}`);
    } catch (e: any) {
      setError(e.message || 'Failed to save application');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!confirm('Are you sure you want to delete this application? Associations will be removed but usecases will not be deleted.')) return;
    setDeleting(true);
    try {
      await api.delete(`applications/${id}`);
      navigate('/applications');
    } catch (e: any) {
      setError(e.message || 'Failed to delete application');
    } finally {
      setDeleting(false);
    }
  }

  function addEnvironment() {
    const env = envInput.trim();
    if (env && !environments.includes(env)) {
      setEnvironments([...environments, env]);
    }
    setEnvInput('');
  }

  if (loading) {
    return <Box textAlign="center" padding="xxl"><Spinner size="large" /></Box>;
  }

  return (
    <SpaceBetween size="l">
      <BreadcrumbGroup
        items={[
          { text: 'Applications', href: '/applications' },
          { text: name || 'Edit', href: `/applications/${id}` },
          { text: 'Edit', href: '#' },
        ]}
        onFollow={(event) => { event.preventDefault(); navigate(event.detail.href); }}
      />

      <Header
        variant="h1"
        actions={
          <SpaceBetween direction="horizontal" size="xs">
            <Button onClick={() => navigate(`/applications/${id}`)}>Cancel</Button>
            <Button variant="primary" loading={saving} onClick={handleSave}>Save</Button>
          </SpaceBetween>
        }
      >
        Edit Application
      </Header>

      {error && <Alert type="error" dismissible onDismiss={() => setError('')}>{error}</Alert>}

      <Container>
        <SpaceBetween size="l">
          <FormField label="Name" constraintText="Required">
            <Input value={name} onChange={({ detail }) => setName(detail.value)} disabled={saving} />
          </FormField>

          <FormField label="Base URL" constraintText="Required">
            <Input value={baseUrl} onChange={({ detail }) => setBaseUrl(detail.value)} disabled={saving} />
          </FormField>

          <FormField label="Description">
            <Textarea value={description} onChange={({ detail }) => setDescription(detail.value)} disabled={saving} />
          </FormField>

          <FormField label="Team">
            <Input value={team} onChange={({ detail }) => setTeam(detail.value)} disabled={saving} />
          </FormField>

          <FormField label="Environments">
            <SpaceBetween size="xs">
              <SpaceBetween direction="horizontal" size="xs">
                <Input
                  value={envInput}
                  onChange={({ detail }) => setEnvInput(detail.value)}
                  placeholder="e.g. production"
                  onKeyDown={({ detail }) => { if (detail.key === 'Enter') addEnvironment(); }}
                  disabled={saving}
                />
                <Button onClick={addEnvironment} iconName="add-plus" disabled={saving}>Add</Button>
              </SpaceBetween>
              <TokenGroup
                items={environments.map(env => ({ label: env, dismissLabel: `Remove ${env}` }))}
                onDismiss={({ detail }) => setEnvironments(environments.filter((_, i) => i !== detail.itemIndex))}
              />
            </SpaceBetween>
          </FormField>
        </SpaceBetween>
      </Container>

      <Container header={<Header variant="h2">Danger Zone</Header>}>
        <Button variant="link" loading={deleting} onClick={handleDelete}>
          Delete this application
        </Button>
      </Container>
    </SpaceBetween>
  );
}
