import { useState, useEffect } from 'react';
import { modelsApi, ModelResponse } from '../utils/api';
import { SelectProps } from '@cloudscape-design/components/select';

export function useModels() {
  const [models, setModels] = useState<ModelResponse[]>([]);
  const [defaultModel, setDefaultModel] = useState<string>('nova-act-v1.0');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchModels = async () => {
      try {
        setLoading(true);
        const response = await modelsApi.list();
        setModels(response.models || []);
        setDefaultModel(response.defaultModel || 'nova-act-v1.0');
      } catch (err) {
        console.error('Failed to fetch models:', err);
        setError('Failed to load models');
        // Set default model as fallback
        setModels([{
          modelId: 'nova-act-v1.0',
          modelName: 'nova-act-v1.0',
          isDefault: true,
          description: 'Default Nova Act model'
        }]);
      } finally {
        setLoading(false);
      }
    };

    fetchModels();
  }, []);

  const modelOptions = (): SelectProps.Option[] => {
    return (models || []).map(model => ({
      label: model.modelName,
      value: model.modelId,
      description: model.description,
      tags: model.isDefault ? ['Default'] : undefined
    }));
  };

  const findModelOption = (modelId?: string): SelectProps.Option => {
    const targetModelId = modelId || defaultModel;
    const model = (models || []).find(m => m.modelId === targetModelId);
    
    if (model) {
      return {
        label: model.modelName,
        value: model.modelId,
        description: model.description,
        tags: model.isDefault ? ['Default'] : undefined
      };
    }

    // Fallback to default
    return {
      label: defaultModel,
      value: defaultModel,
      tags: ['Default']
    };
  };

  return {
    models,
    defaultModel,
    loading,
    error,
    modelOptions,
    findModelOption
  };
}
