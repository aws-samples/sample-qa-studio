import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Container from "@cloudscape-design/components/container";
import Header from "@cloudscape-design/components/header";
import SpaceBetween from "@cloudscape-design/components/space-between";
import Button from "@cloudscape-design/components/button";
import FormField from "@cloudscape-design/components/form-field";
import Input from "@cloudscape-design/components/input";
import Textarea from "@cloudscape-design/components/textarea";
import Checkbox from "@cloudscape-design/components/checkbox";
import { api } from '../utils/api';

export default function CreateUsecase() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [startingUrl, setStartingUrl] = useState('');
  const [active, setActive] = useState(true);
  const [tags, setTags] = useState('');
  const [headless, setHeadless] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    setLoading(true);
    try {
      await api.post('usecase', { 
        name, 
        description, 
        starting_url: startingUrl,
        active,
        headless,
        tags: tags.split(',').map(tag => tag.trim()).filter(tag => tag)
      });
      navigate('/');
    } catch (error) {
      console.error('Failed to create usecase:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container header={<Header variant="h1">Create New Use Case</Header>}>
      <SpaceBetween direction="vertical" size="l">
        <FormField label="Name">
          <Input
            value={name}
            onChange={({ detail }) => setName(detail.value)}
            placeholder="Enter use case name"
          />
        </FormField>
        
        <FormField label="Description">
          <Textarea
            value={description}
            onChange={({ detail }) => setDescription(detail.value)}
            placeholder="Enter use case description"
            rows={4}
          />
        </FormField>
        
        <FormField label="Starting URL">
          <Input
            value={startingUrl}
            onChange={({ detail }) => setStartingUrl(detail.value)}
            placeholder="https://example.com"
          />
        </FormField>
        
        <FormField label="Tags">
          <Input
            value={tags}
            onChange={({ detail }) => setTags(detail.value)}
            placeholder="Enter tags separated by commas"
          />
        </FormField>
        
        <FormField>
          <Checkbox
            checked={active}
            onChange={({ detail }) => setActive(detail.checked)}
          >
            Active
          </Checkbox>
        </FormField>
        
        <FormField>
          <Checkbox
            checked={headless}
            onChange={({ detail }) => setHeadless(detail.checked)}
          >
            Headless Mode
          </Checkbox>
        </FormField>
        
        <SpaceBetween direction="horizontal" size="xs">
          <Button variant="primary" onClick={handleSubmit} loading={loading} disabled={loading}>
            Create
          </Button>
          <Button onClick={() => navigate('/')} disabled={loading}>
            Cancel
          </Button>
        </SpaceBetween>
      </SpaceBetween>
    </Container>
  );
}