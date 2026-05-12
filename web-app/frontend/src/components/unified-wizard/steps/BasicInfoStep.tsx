import React, { useEffect } from 'react';
import Container from "@cloudscape-design/components/container";
import SpaceBetween from "@cloudscape-design/components/space-between";
import FormField from "@cloudscape-design/components/form-field";
import Input from "@cloudscape-design/components/input";
import Textarea from "@cloudscape-design/components/textarea";
import Select, { SelectProps } from "@cloudscape-design/components/select";
import Toggle from "@cloudscape-design/components/toggle";
import type { StepProps } from '../types';
import { useModels } from '../../../hooks/useModels';
import { regionOptions, findRegionOptions } from '../../../utils/browser_regions';

export default function BasicInfoStep({ state, dispatch, validationErrors }: StepProps) {
  const { modelOptions, findModelOption, loading: modelsLoading } = useModels();

  // Pre-populate region and model defaults on mount
  useEffect(() => {
    if (!state.basicInfo.executionRegion) {
      const defaultRegion = findRegionOptions();
      if (defaultRegion?.value) {
        dispatch({ type: 'UPDATE_BASIC_INFO', payload: { executionRegion: defaultRegion.value } });
      }
    }
  }, []);

  useEffect(() => {
    if (!modelsLoading && !state.basicInfo.modelId) {
      const defaultModel = findModelOption();
      if (defaultModel?.value) {
        dispatch({ type: 'UPDATE_BASIC_INFO', payload: { modelId: defaultModel.value } });
      }
    }
  }, [modelsLoading]);

  const selectedRegion = regionOptions().find(
    (opt) => opt.value === state.basicInfo.executionRegion
  ) || null;

  const selectedModel = modelOptions().find(
    (opt) => opt.value === state.basicInfo.modelId
  ) || (state.basicInfo.modelId ? { label: state.basicInfo.modelId, value: state.basicInfo.modelId } : null);

  return (
    <Container>
      <SpaceBetween direction="vertical" size="l">
        <FormField
          label="Name"
          errorText={validationErrors.name}
        >
          <Input
            value={state.basicInfo.name}
            onChange={({ detail }) =>
              dispatch({ type: 'UPDATE_BASIC_INFO', payload: { name: detail.value } })
            }
            placeholder="Enter use case name"
          />
        </FormField>

        <FormField label="Description">
          <Textarea
            value={state.basicInfo.description}
            onChange={({ detail }) =>
              dispatch({ type: 'UPDATE_BASIC_INFO', payload: { description: detail.value } })
            }
            placeholder="Enter use case description"
            rows={4}
          />
        </FormField>

        <FormField
          label="Tags"
          constraintText="Comma-separated tags"
        >
          <Input
            value={state.basicInfo.tags}
            onChange={({ detail }) =>
              dispatch({ type: 'UPDATE_BASIC_INFO', payload: { tags: detail.value } })
            }
            placeholder="Enter tags separated by commas"
          />
        </FormField>

        {state.testPlatform === 'web' && (
          <FormField
            label="Starting URL"
            description="The URL where the test should begin"
            errorText={validationErrors.startingUrl}
          >
            <Input
              value={state.basicInfo.startingUrl}
              onChange={({ detail }) =>
                dispatch({ type: 'UPDATE_BASIC_INFO', payload: { startingUrl: detail.value } })
              }
              placeholder="https://example.com"
              type="url"
            />
          </FormField>
        )}

        <FormField label="Execution Region" errorText={validationErrors.executionRegion}>
          <Select
            selectedOption={selectedRegion}
            onChange={({ detail }) =>
              dispatch({
                type: 'UPDATE_BASIC_INFO',
                payload: { executionRegion: detail.selectedOption.value ?? '' },
              })
            }
            options={regionOptions()}
            placeholder="Select a region"
          />
        </FormField>

        <FormField
          label="Model"
          description="Select the Nova Act model to use for this use case"
          errorText={validationErrors.modelId}
        >
          <Select
            selectedOption={selectedModel}
            onChange={({ detail }) =>
              dispatch({
                type: 'UPDATE_BASIC_INFO',
                payload: { modelId: detail.selectedOption.value ?? null },
              })
            }
            options={modelOptions() || []}
            placeholder="Select a model"
            loadingText="Loading models..."
            statusType={modelsLoading ? "loading" : "finished"}
          />
        </FormField>

        <FormField label="Active">
          <Toggle
            checked={state.basicInfo.active}
            onChange={({ detail }) =>
              dispatch({ type: 'UPDATE_BASIC_INFO', payload: { active: detail.checked } })
            }
          >
            Active
          </Toggle>
        </FormField>
      </SpaceBetween>
    </Container>
  );
}
