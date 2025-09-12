import React, { useState, useEffect, useCallback, Suspense } from 'react';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import Button from "@cloudscape-design/components/button";
import SpaceBetween from "@cloudscape-design/components/space-between";
import ExpandableSection from "@cloudscape-design/components/expandable-section";
import FormField from "@cloudscape-design/components/form-field";
import { api } from '../../utils/api';
import { ContainerLoading } from '../common/LoadingStates';

// Lazy load the code editor to reduce bundle size
const LazyCodeEditor = React.lazy(() => import('../common/LazyCodeEditor'));

interface UsecaseHooksProps {
  usecaseId: string;
}

interface HooksData {
  before_script: string;
  after_script: string;
}

export default function UsecaseHooks({ usecaseId }: UsecaseHooksProps) {
  const [hooks, setHooks] = useState<HooksData>({ before_script: '', after_script: '' });
  const [localHooks, setLocalHooks] = useState<HooksData>({ before_script: '', after_script: '' });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch hooks data
  const fetchHooks = useCallback(async () => {
    if (!usecaseId) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const response = await api.get(`usecase/${usecaseId}/hooks`);
      const hooksData = {
        before_script: response.before_script || '',
        after_script: response.after_script || ''
      };
      setHooks(hooksData);
      setLocalHooks(hooksData);
    } catch (err: any) {
      console.error('Failed to fetch hooks:', err);
      
      // Don't show error for 404 - just means no hooks exist yet
      if (err?.response?.status === 404 || err?.status === 404) {
        const emptyHooks = { before_script: '', after_script: '' };
        setHooks(emptyHooks);
        setLocalHooks(emptyHooks);
      } else {
        setError('Failed to load hooks');
      }
    } finally {
      setLoading(false);
    }
  }, [usecaseId]);

  // Fetch hooks when usecaseId changes
  useEffect(() => {
    fetchHooks();
  }, [fetchHooks]);

  // Handle saving hooks
  const handleSaveHooks = useCallback(async () => {
    setSaving(true);
    setError(null);
    
    try {
      await api.post(`usecase/${usecaseId}/hooks`, localHooks);
      setHooks(localHooks); // Update the server state
      console.log('Hooks saved successfully');
    } catch (err: any) {
      console.error('Failed to save hooks:', err);
      setError('Failed to save hooks. Please try again.');
    } finally {
      setSaving(false);
    }
  }, [usecaseId, localHooks]);

  // Handle updating before script
  const handleBeforeScriptChange = useCallback((value: string) => {
    setLocalHooks(prev => ({ ...prev, before_script: value }));
  }, []);

  // Handle updating after script
  const handleAfterScriptChange = useCallback((value: string) => {
    setLocalHooks(prev => ({ ...prev, after_script: value }));
  }, []);

  // Check if there are unsaved changes
  const hasUnsavedChanges = JSON.stringify(hooks) !== JSON.stringify(localHooks);

  if (loading) {
    return (
      <ContainerLoading 
        title="Hooks"
        text="Loading hooks..."
      />
    );
  }

  return (
    <Container
      header={
        <Header
          variant="h2"
          description="Execute custom Python code before and after workflow execution. Before hook runs in the same shell like your"
          actions={
            <SpaceBetween direction="horizontal" size="xs">
              <Button
                iconName="refresh"
                onClick={fetchHooks}
                disabled={loading || saving}
                ariaLabel="Refresh hooks"
              />
              {hasUnsavedChanges && (
                <Button
                  variant="link"
                  onClick={() => setLocalHooks(hooks)}
                >
                  Reset Changes
                </Button>
              )}
              <Button
                variant="primary"
                onClick={handleSaveHooks}
                loading={saving}
                disabled={saving || !hasUnsavedChanges}
              >
                {saving ? 'Saving...' : hasUnsavedChanges ? 'Save Changes' : 'Saved'}
              </Button>
            </SpaceBetween>
          }
        />
      }
    >
      <SpaceBetween direction="vertical" size="m">
        {error && (
          <div style={{ 
            padding: '12px', 
            backgroundColor: '#ffeaea', 
            border: '1px solid #ff6b6b', 
            borderRadius: '4px',
            color: '#d63031'
          }}>
            {error}
          </div>
        )}

        <ExpandableSection 
          headerText="Before Hook"
          description="Execute code before the workflow execution starts"
          defaultExpanded={!!localHooks.before_script}
        >
          <FormField 
            label="Python Script"
            description="This script will run before the workflow execution begins, within the same shell environment"
          >
            <Suspense fallback={<div>Loading code editor...</div>}>
              <LazyCodeEditor
                value={localHooks.before_script}
                onChange={({ detail }) => handleBeforeScriptChange(detail.value)}
                language="python"
                editorContentHeight={200}
                loading={false}
              />
            </Suspense>
          </FormField>
        </ExpandableSection>

        <ExpandableSection 
          headerText="After Hook"
          description="Execute code after the workflow execution completes"
          defaultExpanded={!!localHooks.after_script}
        >
          <FormField 
            label="Python Script"
            description="This script will run after the workflow execution completes, within the same shell environment"
          >
            <Suspense fallback={<div>Loading code editor...</div>}>
              <LazyCodeEditor
                value={localHooks.after_script}
                onChange={({ detail }) => handleAfterScriptChange(detail.value)}
                language="python"
                editorContentHeight={200}
                loading={false}
              />
            </Suspense>
          </FormField>
        </ExpandableSection>
      </SpaceBetween>
    </Container>
  );
}