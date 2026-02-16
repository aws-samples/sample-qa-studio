import { fetchAuthSession } from 'aws-amplify/auth';
import { errorManager, ErrorState } from './errorManager';

function buildRestEndpoint(path: string): string {
  let endpoint = `/api/`
  const apiEndpoint = __APP_CONFIG__.apiEndpoint;

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
    
    // Use ID token for user authentication with custom scope claim
    // The pre-token generation Lambda adds scopes to the ID token based on user groups
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
    // Use ID token with custom scope claim
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
  groups?: string[];
}

export interface CreateUserRequest {
  email: string;
  groups: string[];
}

export interface CreateUserResponse {
  username: string;
  email: string;
  status: string;
  groups: string[];
}

export const userApi = {
  list: (): Promise<{ users: User[] }> => api.get('users'),
  create: (userData: CreateUserRequest): Promise<CreateUserResponse> => api.post('users', userData),
  delete: (username: string): Promise<void> => api.delete(`users/${encodeURIComponent(username)}`),
};

// OAuth Client API
export interface OAuthClient {
  client_id: string;
  client_name: string;
  created_date: string;
  last_modified_date?: string;
  created_by?: string;
  refresh_token_validity?: number;
  access_token_validity?: number;
  id_token_validity?: number;
  token_validity_units?: {
    AccessToken?: string;
    IdToken?: string;
    RefreshToken?: string;
  };
  explicit_auth_flows?: string[];
  allowed_oauth_flows?: string[];
  allowed_oauth_scopes?: string[];
  enabled: boolean;
}

export interface CreateOAuthClientRequest {
  name: string;
  scopes?: string[];
}

export interface CreateOAuthClientResponse {
  client_id: string;
  client_name: string;
  client_secret: string;
  scopes: string[];
  created_date: string;
  refresh_token_validity?: number;
  access_token_validity?: number;
  id_token_validity?: number;
}

export interface ScopeOption {
  value: string;
  label: string;
  description: string;
}

export interface ListScopesResponse {
  scopes: ScopeOption[];
  resource_server_identifier: string;
}

export const oauthClientApi = {
  list: (): Promise<{ clients: OAuthClient[]; count: number }> => api.get('oauth-clients'),
  create: (clientData: CreateOAuthClientRequest): Promise<CreateOAuthClientResponse> => api.post('oauth-clients', clientData),
  delete: (clientId: string): Promise<void> => api.delete(`oauth-clients/${encodeURIComponent(clientId)}`),
};

export const scopesApi = {
  list: (): Promise<ListScopesResponse> => {
    // Public endpoint - no authentication required
    return fetch(buildRestEndpoint('scopes'), {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    }).then(response => {
      if (!response.ok) {
        throw new Error('Failed to fetch scopes');
      }
      return response.json();
    });
  }
};

// Test Suite API
export interface TestSuite {
  id: string;
  name: string;
  description: string;
  scope: string;
  tags: string[];
  created_at: string;
  updated_at: string;
  created_by: string;
  total_usecases: number;
  last_execution_id?: string;
  last_execution_status?: 'completed' | 'partial' | 'failed';
  last_execution_time?: string;
  last_successful_count?: number;
  schedule_expression?: string;
  schedule_enabled: boolean;
  schedule_timezone?: string;
}

export interface SuiteExecution {
  id: string;
  suite_id: string;
  suite_name: string;
  suite_scope: string;
  status: 'pending' | 'running' | 'completed' | 'partial' | 'failed';
  started_at: string;
  completed_at?: string;
  duration_seconds?: number;
  triggered_by: string;
  trigger_type: 'manual' | 'scheduled';
  total_usecases: number;
  completed_usecases: number;
  successful_usecases: number;
  failed_usecases: number;
  running_usecases: number;
  results?: SuiteExecutionResult[];
}

export interface SuiteExecutionResult {
  usecase_id: string;
  usecase_name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  usecase_execution_id: string;
  started_at?: string;
  completed_at?: string;
  duration_seconds?: number;
  error_message?: string;
  recording_url?: string;
}

export interface CreateTestSuiteRequest {
  name: string;
  description: string;
  scope?: string;  // Optional - will be auto-generated from name if not provided
  tags: string[];
}

export interface UpdateTestSuiteRequest {
  name?: string;
  description?: string;
  tags?: string[];
}

export interface AddUsecasesRequest {
  usecase_ids: string[];
}

export interface AddUsecasesResponse {
  added: number;
  total_usecases: number;
}

export interface ScheduleConfig {
  schedule_expression: string;
  schedule_enabled: boolean;
  schedule_timezone?: string;
}

export interface ExecuteSuiteRequest {
  trigger_type?: 'manual' | 'scheduled';
}

export interface ExecuteSuiteResponse {
  suite_execution_id: string;
  status: string;
  total_usecases: number;
  started_at: string;
}

export const testSuites = {
  // Suite Management
  create: (data: CreateTestSuiteRequest): Promise<TestSuite> => 
    api.post('test-suites', data),
  
  list: (params?: { tag?: string; scope?: string }): Promise<{ suites: TestSuite[] }> => {
    const queryParams = new URLSearchParams();
    if (params?.tag) queryParams.append('tag', params.tag);
    if (params?.scope) queryParams.append('scope', params.scope);
    const query = queryParams.toString();
    return api.get(`test-suites${query ? `?${query}` : ''}`);
  },
  
  get: (suiteId: string): Promise<TestSuite> => 
    api.get(`test-suites/${suiteId}`),
  
  update: (suiteId: string, data: UpdateTestSuiteRequest): Promise<TestSuite> => 
    api.put(`test-suites/${suiteId}`, data),
  
  delete: (suiteId: string): Promise<void> => 
    api.delete(`test-suites/${suiteId}`),
  
  // Use Case Management
  addUsecases: (suiteId: string, data: AddUsecasesRequest): Promise<AddUsecasesResponse> => 
    api.post(`test-suites/${suiteId}/usecases`, data),
  
  listUsecases: (suiteId: string): Promise<{ usecases: any[] }> => 
    api.get(`test-suites/${suiteId}/usecases`),
  
  removeUsecase: (suiteId: string, usecaseId: string): Promise<void> => 
    api.delete(`test-suites/${suiteId}/usecases/${usecaseId}`),
  
  // Schedule Management
  updateSchedule: (suiteId: string, config: ScheduleConfig): Promise<TestSuite> => 
    api.put(`test-suites/${suiteId}/schedule`, config),
  
  // Execution Management
  execute: (suiteId: string, data?: ExecuteSuiteRequest): Promise<ExecuteSuiteResponse> => 
    api.post(`test-suites/${suiteId}/execute`, data || { trigger_type: 'manual' }),
  
  listExecutions: (suiteId: string, params?: { limit?: number; status?: string }): Promise<{ executions: SuiteExecution[] }> => {
    const queryParams = new URLSearchParams();
    if (params?.limit) queryParams.append('limit', params.limit.toString());
    if (params?.status) queryParams.append('status', params.status);
    const query = queryParams.toString();
    return api.get(`test-suites/${suiteId}/executions${query ? `?${query}` : ''}`);
  },
  
  getExecution: (suiteId: string, executionId: string): Promise<SuiteExecution> => 
    api.get(`test-suites/${suiteId}/executions/${executionId}`),
};