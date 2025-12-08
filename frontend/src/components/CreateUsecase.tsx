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
import Select, {SelectProps} from "@cloudscape-design/components/select";
import BreadcrumbGroup from "@cloudscape-design/components/breadcrumb-group";
import { api } from '../utils/api';
import { regionOptions, findRegionOptions } from '../utils/browser_regions';
import { useModels } from '../hooks/useModels';

export default function CreateUsecase() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [startingUrl, setStartingUrl] = useState('');
  const [active, setActive] = useState(true);
  const [tags, setTags] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedRegion, setSelectedRegion] = useState(findRegionOptions() as SelectProps.Option);
  const { modelOptions, findModelOption, loading: modelsLoading } = useModels();
  const [selectedModel, setSelectedModel] = useState<SelectProps.Option | null>(null);

  // Set default model once models are loaded
  React.useEffect(() => {
    if (!modelsLoading && !selectedModel) {
      setSelectedModel(findModelOption());
    }
  }, [modelsLoading, selectedModel, findModelOption]);

  const handleSubmit = async () => {
    setLoading(true);
    try {
      await api.post('usecase', { 
        name, 
        description, 
        starting_url: startingUrl,
        active,
        region: selectedRegion.value,
        model_id: selectedModel?.value,
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
    <SpaceBetween direction="vertical" size="l">
      <BreadcrumbGroup
        items={[
          { text: 'Home', href: '/' },
          { text: 'Create Use Case', href: '/create' },
          { text: 'Create Blank', href: '/create/blank' }
        ]}
        onFollow={(event) => {
          event.preventDefault();
          navigate(event.detail.href);
        }}
      />

      <Header
        variant="h1"
        description="Start from scratch and manually configure all use case settings, steps, and validations."
      >
        Create Blank
      </Header>

      <Container>
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

              <FormField label="Region">
        <Select
          selectedOption={selectedRegion}
          onChange={({ detail }) =>
            setSelectedRegion(detail.selectedOption)
          }
          options={regionOptions()}
        />
      </FormField>

      <FormField 
        label="Model"
        description="Select the Nova Act model to use for this use case"
      >
        <Select
          selectedOption={selectedModel}
          onChange={({ detail }) =>
            setSelectedModel(detail.selectedOption)
          }
          options={modelOptions()}
          placeholder="Select a model"
          loadingText="Loading models..."
          statusType={modelsLoading ? "loading" : "finished"}
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
        
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="primary" onClick={handleSubmit} loading={loading} disabled={loading}>
              Create
            </Button>
            <Button onClick={() => navigate('/create')} disabled={loading}>
              Cancel
            </Button>
          </SpaceBetween>
        </SpaceBetween>
      </Container>
    </SpaceBetween>
  );
}