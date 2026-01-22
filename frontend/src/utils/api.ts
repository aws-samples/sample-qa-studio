import { fetchAuthSession } from 'aws-amplify/auth';
import { errorManager, ErrorState } from './errorManager';
import { apiEndpoint } from '../../../configuration.json'

function buildRestEndpoint(path: string): string {
  let endpoint = `/api/`

  if(apiEndpoint.startsWith('https://') && apiEndpoint.endsWith('/')) {
    endpoint = apiEndpoint
  }

  if(apiEndpoint.startsWith('https://') && !apiEndpoint.endsWith('/')) {
    endpoint = `${apiEndpoint}/`
  }

  return `${endpoint}${path}`
}

export interface ExecutionModel {
  pk: string;
  sk: string;
  status: string;
  starting_url: string;
  createdAt: string;
  completedAt: string;
  executingAt: string;
  triggerType: string;
  novaActSessionId: string;
}

export const apiRequest = async (endpoint: string, options: RequestInit = {}) => {
  try {
    const session = await fetchAuthSession();
    const token = session.tokens?.idToken?.toString();

    if (!token) {
      throw errorManager.createError('authentication', 'No authentication token available');
    }

    const response = await fetch(buildRestEndpoint(endpoint), {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        ...options.headers,
      },
    });

    if (!response.ok) {
      let errorData: any = {};
      try {
        errorData = await response.json();
      } catch {
        // Response is not JSON
      }

      const error = errorManager.categorizeHttpError(
        response.status,
        errorData.error || errorData.message
      );

      if (errorData.details) {
        error.details = errorData.details;
      }

      if (errorData.code) {
        error.code = errorData.code;
      }

      throw error;
    }

    // Handle responses with no content (like 204 No Content)
    if (response.status === 204 || response.headers.get('content-length') === '0') {
      return null;
    }

    // Check if response has JSON content
    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      return await response.json();
    }

    // For non-JSON responses, return the text
    return await response.text();
  } catch (error) {
    // If it's already an ErrorState, re-throw it
    if ((error as ErrorState).type) {
      throw error;
    }

    // Convert unknown errors to network errors
    console.error('API request failed:', error);
    throw errorManager.createError('network',
      'Network request failed. Please check your connection and try again.',
      { details: (error as Error).message }
    );
  }
};

export const api = {
  get: (endpoint: string) => apiRequest(endpoint, { method: 'GET' }),
  post: (endpoint: string, data: any) => apiRequest(endpoint, {
    method: 'POST',
    body: JSON.stringify(data)
  }),
  patch: (endpoint: string, data: any) => apiRequest(endpoint, {
    method: 'PATCH',
    body: JSON.stringify(data)
  }),
  put: (endpoint: string, data: any) => apiRequest(endpoint, {
    method: 'PUT',
    body: JSON.stringify(data)
  }),
  delete: (endpoint: string, data?: any) => apiRequest(endpoint, {
    method: 'DELETE',
    ...(data && { body: JSON.stringify(data) })
  }),
};

export const hooksApi = {
  get: (usecaseId: string) => api.get(`usecase/${usecaseId}/hooks`),
  create: (usecaseId: string, hooks: { before_script: string, after_script: string }) => api.post(`usecase/${usecaseId}/hooks`, hooks),
};

// User Journey Wizard API interfaces
export interface GenerateUsecaseRequest {
  title: string;
  starting_url: string;
  userJourney: string;
  region: string;
}

export interface GenerateUsecaseResponse {
  success: boolean;
  usecaseData: string; // JSON string compatible with import_usecase
  message: string;
  error?: string;
}

export interface ApiError {
  type: 'validation' | 'network' | 'bedrock' | 'import' | 'unknown';
  message: string;
  retryable: boolean;
  details?: string;
}

// Enhanced API request with retry logic using RetryManager
export const apiRequestWithRetry = async (
  endpoint: string,
  options: RequestInit = {},
  maxRetries: number = 3
): Promise<any> => {
  const operation = () => apiRequest(endpoint, options);

  // Use RetryManager for consistent retry behavior
  const { RetryManager } = await import('./retryManager');
  const result = await RetryManager.executeWithRetry(operation, { maxRetries });

  if (result.success) {
    return result.data;
  } else {
    throw result.error;
  }
};

export const wizardApi = {
  generateUsecase: async (request: GenerateUsecaseRequest): Promise<GenerateUsecaseResponse> => {
    // Validate request before sending
    if (!request.title?.trim()) {
      throw errorManager.createError('validation', 'Use case title is required');
    }

    if (!request.starting_url?.trim()) {
      throw errorManager.createError('validation', 'Starting URL is required');
    }

    if (!request.userJourney?.trim()) {
      throw errorManager.createError('validation', 'User journey description is required');
    }

    if (!request.region?.trim()) {
      throw errorManager.createError('validation', 'Execution region is required');
    }

    // URL validation
    try {
      new URL(request.starting_url);
    } catch {
      throw errorManager.createError('validation',
        'Please enter a valid URL (including http:// or https://)');
    }

    // Length validations
    if (request.title.length > 200) {
      throw errorManager.createError('validation', 'Title must be 200 characters or less');
    }

    if (request.userJourney.length < 50) {
      throw errorManager.createError('validation',
        'User journey description must be at least 50 characters');
    }

    if (request.userJourney.length > 2000) {
      throw errorManager.createError('validation',
        'User journey description must be 2000 characters or less');
    }

    try {
      // Use circuit breaker for Bedrock calls to prevent cascading failures
      const { RetryManager } = await import('./retryManager');
      const result = await RetryManager.executeWithCircuitBreaker(
        () => apiRequest('generate-usecase', {
          method: 'POST',
          body: JSON.stringify(request)
        }),
        'bedrock-generate-usecase',
        { maxRetries: 2 } // Limit retries for expensive Bedrock calls
      );

      if (result.success) {
        return result.data;
      } else {
        // Enhance Bedrock-specific errors
        if (result.error?.type === 'network') {
          result.error.type = 'bedrock';
          result.error.message = 'AI service is temporarily unavailable. Please try again in a moment.';
        }
        throw result.error;
      }
    } catch (error) {
      // If it's already an ErrorState, re-throw it
      if ((error as ErrorState).type) {
        throw error;
      }

      // Convert unknown errors to bedrock errors for this context
      throw errorManager.createError('bedrock',
        'Failed to generate use case with AI. Please try again.',
        { details: (error as Error).message }
      );
    }
  }
};

export const exportImportApi = {
  exportUsecase: async (usecaseId: string) => {
    const session = await fetchAuthSession();
    const token = session.tokens?.idToken?.toString();

    const response = await fetch(buildRestEndpoint(`usecase/${usecaseId}/export`), {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.blob();
  },
  importUsecase: (data: any) => api.post('import', data),
};

export interface SubscriptionStatusResponse {
  is_subscribed: boolean;
  email?: string;
}

export const subscriptionApi = {
  getStatus: async (usecaseId: string): Promise<SubscriptionStatusResponse> => {
    return api.get(`usecase/${usecaseId}/subscription`);
  },
  subscribe: async (usecaseId: string): Promise<SubscriptionStatusResponse> => {
    return api.post(`usecase/${usecaseId}/subscription`, {});
  },
  unsubscribe: async (usecaseId: string): Promise<SubscriptionStatusResponse> => {
    return api.delete(`usecase/${usecaseId}/subscription`);
  },
}

// Models API
export interface ModelResponse {
  modelId: string;
  modelName: string;
  isDefault: boolean;
  description?: string;
}

export interface ListModelsResponse {
  models: ModelResponse[];
  defaultModel: string;
}

export const modelsApi = {
  list: async (): Promise<ListModelsResponse> => {
    return api.get('models');
  },
}

// User Management API
export interface User {
  username: string;
  email: string;
  status: string;
  enabled: boolean;
  created_at: string;
  attributes: { [key: string]: string };
}

export interface CreateUserRequest {
  email: string;
}

export interface CreateUserResponse {
  username: string;
  email: string;
  status: string;
}

export const userApi = {
  list: (): Promise<{ users: User[] }> => api.get('users'),
  create: (userData: CreateUserRequest): Promise<CreateUserResponse> => api.post('users', userData),
  delete: (username: string): Promise<void> => api.delete(`users/${encodeURIComponent(username)}`),
};