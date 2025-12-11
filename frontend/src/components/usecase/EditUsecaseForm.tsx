import React, { useState } from 'react';
import SpaceBetween from "@cloudscape-design/components/space-between";
import FormField from "@cloudscape-design/components/form-field";
import Input from "@cloudscape-design/components/input";
import Textarea from "@cloudscape-design/components/textarea";
import Checkbox from "@cloudscape-design/components/checkbox";
import Button from "@cloudscape-design/components/button";
import Select, { SelectProps } from "@cloudscape-design/components/select";
import { regionOptions, findRegionOptions } from './../../utils/browser_regions';
import { useModels } from '../../hooks/useModels';

interface EditUsecaseFormProps {
  usecase: any;
  onSave: (updatedUsecase: any) => void;
  onCancel: () => void;
}

export default function EditUsecaseForm({ usecase, onSave, onCancel }: EditUsecaseFormProps) {
  const [name, setName] = useState(usecase.name || '');
  const [description, setDescription] = useState(usecase.description || '');
  const [startingUrl, setStartingUrl] = useState(usecase.starting_url || '');
  const [active, setActive] = useState(usecase.active || false);
  const [tags, setTags] = useState(usecase.tags?.join(', ') || '');
  const [selectedRegion, setSelectedRegion] = useState(findRegionOptions(usecase.region) as SelectProps.Option);
  const { modelOptions, findModelOption, loading: modelsLoading } = useModels();
  const [selectedModel, setSelectedModel] = useState<SelectProps.Option | null>(null);

  // Set model from usecase or default
  React.useEffect(() => {
    if (!modelsLoading && !selectedModel) {
      setSelectedModel(findModelOption(usecase.model_id));
    }
  }, [modelsLoading, selectedModel, usecase.model_id, findModelOption]);

  const handleSave = () => {
    const updatedUsecase = {
      name,
      description,
      starting_url: startingUrl,
      active,
      region: selectedRegion.value,
      model_id: selectedModel?.value,
      tags: tags.split(',').map((tag: string) => tag.trim()).filter((tag: string) => tag.length > 0)
    };
    onSave(updatedUsecase);
  };

  return (
    <SpaceBetween direction="vertical" size="m">
      <FormField label="Name">
        <Input
          value={name}
          onChange={({ detail }) => setName(detail.value)}
          placeholder="Enter usecase name"
        />
      </FormField>

      <FormField label="Description">
        <Textarea
          value={description}
          onChange={({ detail }) => setDescription(detail.value)}
          placeholder="Enter usecase description"
          rows={3}
        />
      </FormField>

      <FormField label="Starting URL">
        <Input
          value={startingUrl}
          onChange={({ detail }) => setStartingUrl(detail.value)}
          placeholder="https://example.com"
          type="url"
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
          placeholder="tag1, tag2, tag3"
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
        <Button variant="primary" onClick={handleSave}>
          Save Changes
        </Button>
        <Button onClick={onCancel}>
          Cancel
        </Button>
      </SpaceBetween>
    </SpaceBetween>
  );
}