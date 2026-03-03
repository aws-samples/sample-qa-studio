import { useState } from 'react';
import Modal from "@cloudscape-design/components/modal";
import Box from "@cloudscape-design/components/box";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import FormField from "@cloudscape-design/components/form-field";
import Input from "@cloudscape-design/components/input";
import Textarea from "@cloudscape-design/components/textarea";
import TokenGroup from "@cloudscape-design/components/token-group";
import { api } from '../../utils/api';

interface CreateTemplateModalProps {
  visible: boolean;
  onDismiss: () => void;
  onSuccess: () => void;
}

export default function CreateTemplateModal({ visible, onDismiss, onSuccess }: CreateTemplateModalProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState('');
  const [loading, setLoading] = useState(false);

  const handleCreate = async () => {
    if (!name.trim()) return;

    setLoading(true);
    try {
      await api.post('templates', {
        name: name.trim(),
        description: description.trim(),
        tags: tags
      });
      
      // Reset form
      setName('');
      setDescription('');
      setTags([]);
      setTagInput('');
      
      onSuccess();
    } catch (error) {
      console.error('Failed to create template:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddTag = () => {
    if (tagInput.trim() && !tags.includes(tagInput.trim())) {
      setTags([...tags, tagInput.trim()]);
      setTagInput('');
    }
  };

  return (
    <Modal
      visible={visible}
      onDismiss={onDismiss}
      header="Create Template"
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={onDismiss}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleCreate}
              disabled={!name.trim() || loading}
              loading={loading}
            >
              Create
            </Button>
          </SpaceBetween>
        </Box>
      }
    >
      <SpaceBetween direction="vertical" size="l">
        <FormField label="Name" description="A descriptive name for your template">
          <Input
            value={name}
            onChange={({ detail }) => setName(detail.value)}
            placeholder="e.g., Login Flow"
          />
        </FormField>

        <FormField label="Description" description="What does this template do?">
          <Textarea
            value={description}
            onChange={({ detail }) => setDescription(detail.value)}
            placeholder="e.g., Standard username/password login with validation"
            rows={3}
          />
        </FormField>

        <FormField label="Tags" description="Add tags to help find this template later">
          <SpaceBetween direction="vertical" size="xs">
            <div style={{ display: 'flex', gap: '8px' }}>
              <Input
                value={tagInput}
                onChange={({ detail }) => setTagInput(detail.value)}
                onKeyDown={(e) => {
                  if (e.detail.key === 'Enter') {
                    e.preventDefault();
                    handleAddTag();
                  }
                }}
                placeholder="Enter a tag and press Enter"
              />
              <Button onClick={handleAddTag}>Add</Button>
            </div>
            {tags.length > 0 && (
              <TokenGroup
                items={tags.map(tag => ({ label: tag, dismissLabel: `Remove ${tag}` }))}
                onDismiss={({ detail }) => {
                  setTags(tags.filter((_, index) => index !== detail.itemIndex));
                }}
              />
            )}
          </SpaceBetween>
        </FormField>
      </SpaceBetween>
    </Modal>
  );
}
