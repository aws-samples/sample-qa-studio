import React, { useState, useEffect } from 'react';
import Modal from '@cloudscape-design/components/modal';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';
import FormField from '@cloudscape-design/components/form-field';
import Input from '@cloudscape-design/components/input';
import Textarea from '@cloudscape-design/components/textarea';
import Select, { SelectProps } from '@cloudscape-design/components/select';
import TokenGroup from '@cloudscape-design/components/token-group';
import Alert from '@cloudscape-design/components/alert';
import { Application } from '../../types/application';
import { api } from '../../utils/api';
import { usePermissions } from '../../auth';
import { useTeamOptions } from '../../hooks/useTeamOptions';

const APP_CREATOR_ROLES = ['team_lead'] as const;

interface CreateApplicationModalProps {
  visible: boolean;
  onDismiss: () => void;
  onSuccess: () => void;
  editApplication?: Application;
}

export function CreateApplicationModal({ visible, onDismiss, onSuccess, editApplication }: CreateApplicationModalProps) {
  const { isAdmin } = usePermissions();
  const [name, setName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [description, setDescription] = useState('');
  const [selectedTeam, setSelectedTeam] = useState<SelectProps.Option | null>(null);
  // Non-admins: only teams they lead (a Team Lead creates apps for their team)
  const teamOptions = useTeamOptions(visible, APP_CREATOR_ROLES);
  const [environments, setEnvironments] = useState<string[]>([]);
  const [envInput, setEnvInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isAdmin && teamOptions.length === 1 && !editApplication) {
      setSelectedTeam(teamOptions[0]);
    }
  }, [teamOptions, isAdmin, editApplication]);

  useEffect(() => {
    if (editApplication) {
      setName(editApplication.name);
      setBaseUrl(editApplication.base_url);
      setDescription(editApplication.description);
      const ownerTeamId = (editApplication as any).owner_team_id || '';
      const teamName = (editApplication as any).team || '';
      setSelectedTeam(ownerTeamId ? { label: teamName || ownerTeamId, value: ownerTeamId } : null);
      setEnvironments(editApplication.environments || []);
    } else {
      setName('');
      setBaseUrl('');
      setDescription('');
      setSelectedTeam(null);
      setEnvironments([]);
    }
    setError('');
  }, [editApplication, visible]);

  async function handleSubmit() {
    if (!name.trim()) {
      setError('Name is required');
      return;
    }
    if (!baseUrl.trim()) {
      setError('Base URL is required');
      return;
    }
    if (!editApplication && !selectedTeam?.value) {
      setError('Team is required');
      return;
    }

    setSaving(true);
    setError('');

    try {
      const payload = { name, base_url: baseUrl, description, team: selectedTeam?.label || '', teamId: selectedTeam?.value || '', environments };

      if (editApplication) {
        await api.patch(`applications/${editApplication.id}`, payload);
      } else {
        await api.post('applications', payload);
      }

      onSuccess();
      onDismiss();
    } catch (e: any) {
      setError(e.message || 'Failed to save application');
    } finally {
      setSaving(false);
    }
  }

  function addEnvironment() {
    const env = envInput.trim();
    if (env && !environments.includes(env)) {
      setEnvironments([...environments, env]);
    }
    setEnvInput('');
  }

  return (
    <Modal
      visible={visible}
      onDismiss={onDismiss}
      header={editApplication ? 'Edit Application' : 'Create Application'}
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={onDismiss}>Cancel</Button>
            <Button variant="primary" loading={saving} onClick={handleSubmit}>
              {editApplication ? 'Save' : 'Create'}
            </Button>
          </SpaceBetween>
        </Box>
      }
    >
      <SpaceBetween size="m">
        {error && <Alert type="error">{error}</Alert>}

        <FormField label="Name" constraintText="Required">
          <Input value={name} onChange={({ detail }) => setName(detail.value)} placeholder="My Application" />
        </FormField>

        <FormField label="Base URL" constraintText="Required">
          <Input value={baseUrl} onChange={({ detail }) => setBaseUrl(detail.value)} placeholder="https://app.example.com" />
        </FormField>

        <FormField label="Description">
          <Textarea value={description} onChange={({ detail }) => setDescription(detail.value)} placeholder="Optional description" />
        </FormField>

        <FormField label="Team" description="The team that owns this application" constraintText={editApplication ? undefined : 'Required'}>
          <Select
            selectedOption={selectedTeam}
            onChange={({ detail }) => setSelectedTeam(detail.selectedOption)}
            options={teamOptions}
            placeholder="Select a team"
            empty="No teams available"
          />
        </FormField>

        <FormField label="Environments">
          <SpaceBetween size="xs">
            <SpaceBetween direction="horizontal" size="xs">
              <Input
                value={envInput}
                onChange={({ detail }) => setEnvInput(detail.value)}
                placeholder="e.g. production"
                onKeyDown={({ detail }) => { if (detail.key === 'Enter') addEnvironment(); }}
              />
              <Button onClick={addEnvironment} iconName="add-plus">Add</Button>
            </SpaceBetween>
            <TokenGroup
              items={environments.map(env => ({ label: env, dismissLabel: `Remove ${env}` }))}
              onDismiss={({ detail }) => {
                setEnvironments(environments.filter((_, i) => i !== detail.itemIndex));
              }}
            />
          </SpaceBetween>
        </FormField>
      </SpaceBetween>
    </Modal>
  );
}
