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

/** Execution record as returned by `GET usecase/{id}/executions` (DynamoDB item, snake_case). */
export interface ExecutionModel {
  pk: string;
  sk: string;
  status: string;
  starting_url?: string;
  created_at: string;
  executing_at?: string;
  completed_at?: string;
  trigger_type?: string;
  cloudwatch_logs_url?: string;
}

/** One `{key, value}` row of `GET usecase/{id}/executions/{executionId}/variables`. */
interface ExecutionVariable {
  key: string;
  value: string;
}

/** Response of `GET usecase/{id}/executions/{executionId}/variables` (snake_case). */
export interface ExecutionVariablesResponse {
  /** The use case's current `USECASE_VARIABLES` (kept for compatibility, not the run's values). */
  variables: ExecutionVariable[];
  /** Captured during the run, final value per key. */
  runtime_variables: ExecutionVariable[];
  /** Snapshot of the merged variables the run started with; `{}` when none were recorded. */
  execution_variables: Record<string, string>;
}

const EXECUTION_SK_PREFIX = 'EXECUTION#';

/** The bare execution id of an execution record (`sk` is `EXECUTION#{id}`). */
export function executionIdOf(item: Pick<ExecutionModel, 'sk'>): string {
  return item.sk.startsWith(EXECUTION_SK_PREFIX) ? item.sk.slice(EXECUTION_SK_PREFIX.length) : item.sk;
}

const apiRequest = async (endpoint: string, options: RequestInit = {}) => {
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

      // Keep the raw status and parsed body reachable for callers that act on
      // structured error answers (e.g. `409 {usecases}` on dataset delete).
      (error as ApiHttpError).status = response.status;
      (error as ApiHttpError).body = errorData;

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

// Recording data interfaces (matching stripped NovaActRecorder extension output)
interface Assertion {
  id: string;
  text: string;
  captureScreenshot: boolean;
}

interface ActionEntry {
  id: string;
  type: 'click' | 'dblclick' | 'contextmenu' | 'type' | 'paste' | 'change' | 'pointer' | 'scroll' | 'navigation' | 'tab_switch' | 'intent' | 'extract_variable';
  prompt: string;
  url: string;
  timestamp: number;
  isIntent: boolean;
  assertions: Assertion[];
  variableName?: string;
  selectedText?: string;
  sourceVariableName?: string;
}

interface RecordingSession {
  id: string;
  startedAt: number;
  stoppedAt?: number;
  tabId: number;
  startingUrl: string;
  name?: string;
  actions: ActionEntry[];
}

export interface RecordingData {
  type: string;
  version: string;
  data: {
    session: RecordingSession;
    event_count: number;
    duration_seconds?: number;
  };
  captured_at: string;
  screenshot_manifest_key?: string;
  screenshot_s3_prefix?: string;
}

interface RecordingCommandResponse {
  status: 'command_sent';
  commandId: string;
}

interface RecordingDataResponse {
  status: 'available' | 'not_available' | 'error';
  recording_data: RecordingData | null;
  error?: string | null;
}

// User Journey Wizard API interfaces
interface GenerateUsecaseRequest {
  title: string;
  starting_url: string;
  userJourney: string;
  region: string;
  recording_data?: RecordingData;
}

interface GenerateUsecaseResponse {
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

export const wizardApi = {
  generateUsecase: async (request: GenerateUsecaseRequest): Promise<GenerateUsecaseResponse> => {
    // Validate request before sending
    if (!request.title?.trim()) {
      throw errorManager.createError('validation', 'Use case title is required');
    }

    if (!request.starting_url?.trim()) {
      throw errorManager.createError('validation', 'Starting URL is required');
    }

    if (!request.userJourney?.trim() && !request.recording_data) {
      throw errorManager.createError('validation', 'User journey description is required when no recording data is provided');
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

    // Only validate user journey length if it's actually provided
    if (request.userJourney?.trim()) {
      if (request.userJourney.length < 50) {
        throw errorManager.createError('validation',
          'User journey description must be at least 50 characters');
      }

      if (request.userJourney.length > 2000) {
        throw errorManager.createError('validation',
          'User journey description must be 2000 characters or less');
      }
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
  },

  // The session routes below need the session's usecaseId in the body: the
  // API checks edit on that use case and that the session belongs to it.
  addStep: async (sessionId: string, usecaseId: string, stepData: Record<string, any>) => {
    return api.post(`wizard/${encodeURIComponent(sessionId)}/step`, { ...stepData, usecaseId });
  },
  sendRecordingCommand: async (
    sessionId: string,
    usecaseId: string,
    action: 'recording_start' | 'recording_stop'
  ): Promise<RecordingCommandResponse> => {
    return apiRequest(`wizard/${encodeURIComponent(sessionId)}/command`, {
      method: 'POST',
      body: JSON.stringify({ usecaseId, action }),
    });
  },

  getRecordingData: async (
    sessionId: string,
    usecaseId: string
  ): Promise<RecordingDataResponse> => {
    return apiRequest(
      `wizard/${encodeURIComponent(sessionId)}/recording?usecaseId=${encodeURIComponent(usecaseId)}`
    );
  },
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

interface ListModelsResponse {
  models: ModelResponse[];
  defaultModel: string;
}

export const modelsApi = {
  list: async (): Promise<ListModelsResponse> => {
    return api.get('models');
  },
}

// Device Farm Devices API
interface DeviceFarmDevice {
  arn: string;
  name: string;
  platform: string;
  os: string;
  formFactor: string;
  manufacturer: string;
  modelId: string;
}

interface ListDevicesResponse {
  devices: DeviceFarmDevice[];
}

export const devicesApi = {
  list: async (platform?: string): Promise<ListDevicesResponse> => {
    const query = platform ? `?platform=${platform}` : '';
    return api.get(`devices${query}`);
  },
}

// OAuth Client API
export interface OAuthClient {
  client_id: string;
  client_name: string;
  created_date: string;
  last_modified_date?: string;
  created_by?: string;
  /** Team the client is bound to; null for a legacy unbound client (no access). */
  team_id?: string | null;
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
  /** Owning team (required); the client acts with at most editor rights in it. */
  teamId: string;
}

interface CreateOAuthClientResponse {
  client_id: string;
  client_name: string;
  client_secret: string;
  scopes: string[];
  created_date: string;
  refresh_token_validity?: number;
  access_token_validity?: number;
  id_token_validity?: number;
}

interface RotateSecretResponse {
  client_id: string;
  client_secret: string;
  rotated_at: string;
}

interface ScopeOption {
  value: string;
  label: string;
  description: string;
}

interface ListScopesResponse {
  scopes: ScopeOption[];
  resource_server_identifier: string;
}

export const oauthClientApi = {
  list: (): Promise<{ clients: OAuthClient[]; count: number }> => api.get('oauth-clients'),
  create: (clientData: CreateOAuthClientRequest): Promise<CreateOAuthClientResponse> => api.post('oauth-clients', clientData),
  delete: (clientId: string): Promise<void> => api.delete(`oauth-clients/${encodeURIComponent(clientId)}`),
  rotateSecret: (clientId: string): Promise<RotateSecretResponse> => api.post(`oauth-clients/${encodeURIComponent(clientId)}/rotate-secret`, {}),
};

export const scopesApi = {
  list: async (): Promise<ListScopesResponse> => {
    return apiRequest('scopes');
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
  duration_ms?: number;
  triggered_by: string;
  trigger_type: 'manual' | 'scheduled' | 'ci_runner';
  total_usecases: number;
  completed_usecases: number;
  successful_usecases: number;
  failed_usecases: number;
  running_usecases: number;
  results?: SuiteExecutionResult[];
}

interface SuiteExecutionResult {
  usecase_id: string;
  usecase_name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  usecase_execution_id: string;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
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

interface AddUsecasesRequest {
  usecase_ids: string[];
}

interface AddUsecasesResponse {
  added: number;
  total_usecases: number;
}

export interface ScheduleConfig {
  schedule_expression: string;
  schedule_enabled: boolean;
  schedule_timezone?: string;
}

interface ExecuteSuiteRequest {
  // Suite-level 'OnDemand' is valid: the suite Lambda spawns each use case
  // headless. It differs from the use-case execute endpoint, which only
  // accepts OnDemandHeadless / Scheduled / ci_runner.
  trigger_type?: 'OnDemand' | 'ci_runner';
}

interface ExecuteSuiteResponse {
  suite_execution_id: string;
  status: string;
  total_usecases: number;
  started_at: string;
}

export interface SuiteArtifact {
  filename: string;
  type: string;
  content_type: string;
  download_url: string;
  size: number;
  last_modified: string;
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
    api.post(`test-suites/${suiteId}/execute`, data || { trigger_type: 'OnDemand' }),
  
  listExecutions: (suiteId: string, params?: { limit?: number; status?: string }): Promise<{ executions: SuiteExecution[] }> => {
    const queryParams = new URLSearchParams();
    if (params?.limit) queryParams.append('limit', params.limit.toString());
    if (params?.status) queryParams.append('status', params.status);
    const query = queryParams.toString();
    return api.get(`test-suites/${suiteId}/executions${query ? `?${query}` : ''}`).then((data: any) => ({
      ...data,
      executions: (data.executions || []).map((e: any) => ({
        ...e,
        id: e.suite_execution_id || e.id,
      })),
    }));
  },
  
  getExecution: (suiteId: string, executionId: string): Promise<SuiteExecution> => 
    api.get(`test-suites/${suiteId}/executions/${executionId}`).then((data: any) => ({
      ...data,
      id: data.suite_execution_id || data.id,
    })),

  listArtifacts: (suiteId: string, executionId: string): Promise<{ artifacts: SuiteArtifact[] }> =>
    api.get(`test-suites/${suiteId}/executions/${executionId}/artifacts`),
};

/**
 * Error thrown by the `api.*` helpers for a non-2xx response: the categorized
 * `ErrorState` plus the HTTP status and the parsed JSON body (`{}` when the
 * body was not JSON). Narrow with `(err as Partial<ApiHttpError>).status`.
 */
export interface ApiHttpError extends ErrorState {
  status: number;
  body: Record<string, any>;
}

// Application datasets API (`/applications/{id}/datasets`)
/** List row of `GET /applications/{id}/datasets`: counts instead of the table. */
export interface ApplicationDatasetSummary {
  dataset_id: string;
  name: string;
  description: string;
  column_count: number;
  row_count: number;
  updated_at: string;
}

/** Full dataset record (`GET …/datasets/{datasetId}`, and the `dataset` of create / update). */
export interface ApplicationDataset {
  dataset_id: string;
  name: string;
  description: string;
  columns: string[];
  rows: string[][];
  created_at: string;
  updated_at: string;
  created_by: string;
}

/** Body of create (POST) and update (PUT, full replace). */
export interface ApplicationDatasetRequest {
  name: string;
  description?: string;
  columns: string[];
  rows: string[][];
}

export const datasetsApi = {
  list: (applicationId: string): Promise<{ datasets: ApplicationDatasetSummary[] }> =>
    api.get(`applications/${applicationId}/datasets`),

  get: (applicationId: string, datasetId: string): Promise<{ dataset: ApplicationDataset }> =>
    api.get(`applications/${applicationId}/datasets/${datasetId}`),

  create: (applicationId: string, data: ApplicationDatasetRequest): Promise<{ dataset: ApplicationDataset }> =>
    api.post(`applications/${applicationId}/datasets`, data),

  update: (applicationId: string, datasetId: string, data: ApplicationDatasetRequest): Promise<{ dataset: ApplicationDataset }> =>
    api.put(`applications/${applicationId}/datasets/${datasetId}`, data),

  /** 204 on success; rejects with an `ApiHttpError` whose `body.usecases` lists the referencing use cases on 409. */
  delete: (applicationId: string, datasetId: string): Promise<void> =>
    api.delete(`applications/${applicationId}/datasets/${datasetId}`),
};

// Cost allocation API (`/applications/{id}/costs`, `/usecase/{id}/costs`, `/dashboard/costs`).
// Field names mirror `lambdas/endpoints/cost_models.py` 1:1 (snake_case, as the API returns them).

/** Direction of a window vs. the previous window of the same length (±5 % dead band is `flat`). */
export type CostTrendDirection = 'up' | 'down' | 'flat';

/** One source's share of a ledger row (`cost_models.ServiceCost`). */
export interface ServiceCost {
  /** `nova_act` | `compute` (sources are additive, so a plain string). */
  service: string;
  /** Allocated Cost Explorer bill (USD). */
  cost: number;
  /** usage_seconds / 3600 × list price (USD). */
  list_cost: number;
  usage_seconds: number;
  /** compute only: VM launches. */
  launches?: number | null;
}

/** Bill no use-case row carries; application and overall rows only (`cost_models.Buckets`). */
interface CostBuckets {
  unassigned: number;
  unallocated: number;
  unmetered: number;
}

/** One dimension's cost on one UTC day (`cost_models.LedgerRow`). */
export interface LedgerRow {
  /** `YYYY-MM-DD` */
  date: string;
  /** Cost Explorer "Estimated" flag for that day. */
  estimated: boolean;
  /** Use case rows: roll-up parent on that date. */
  application_id?: string | null;
  cost: ServiceCost[];
  buckets?: CostBuckets | null;
  /** ISO 8601 UTC */
  collected_at: string;
}

/** Flat per-dimension summary (`cost_models.CostSummary`, the `USAGE#… / SUMMARY` item). */
export interface CostSummary {
  /** `YYYY-MM-DD`, newest day included. */
  as_of: string;
  window_1d: number;
  window_1d_trend: CostTrendDirection | null;
  window_1d_change_pct: number | null;
  window_1d_list: number;
  window_7d: number;
  window_7d_trend: CostTrendDirection | null;
  window_7d_change_pct: number | null;
  window_7d_list: number;
  window_30d: number;
  window_30d_trend: CostTrendDirection | null;
  window_30d_change_pct: number | null;
  window_30d_list: number;
  /** service → USD over the 30d window. */
  by_source_30d: Record<string, number>;
  /** Ledger rows this dimension has (UI: "not enough data"). */
  days_available: number;
  /** Rows in the 30d window still "Estimated". */
  estimated_days: number;
  /** ISO 8601 UTC */
  updated_at: string;
}

/** `GET /usecase/{id}/costs` */
export interface UsecaseCostsResponse {
  /** null until the collector has written a SUMMARY item. */
  summary: CostSummary | null;
  /** Last 30 ledger rows, oldest first. */
  days: LedgerRow[];
}

/** Row of `ApplicationCostsResponse.usecases`. */
export interface ApplicationUsecaseCost {
  usecase_id: string;
  name: string;
  summary: CostSummary | null;
}

/** `GET /applications/{id}/costs` */
export interface ApplicationCostsResponse extends UsecaseCostsResponse {
  usecases: ApplicationUsecaseCost[];
}

/** Row of `DashboardCostsResponse.applications`. */
export interface DashboardApplicationCost {
  application_id: string;
  summary: CostSummary | null;
}

/** `GET /dashboard/costs` (rows filtered to the applications the caller may view). */
export interface DashboardCostsResponse {
  overall: CostSummary | null;
  applications: DashboardApplicationCost[];
}

export const costsApi = {
  /** Rejects with an `ApiHttpError` (`status` 403/404) when the caller may not view the application. */
  application: (applicationId: string): Promise<ApplicationCostsResponse> =>
    api.get(`applications/${encodeURIComponent(applicationId)}/costs`),

  usecase: (usecaseId: string): Promise<UsecaseCostsResponse> =>
    api.get(`usecase/${encodeURIComponent(usecaseId)}/costs`),

  dashboard: (): Promise<DashboardCostsResponse> =>
    api.get('dashboard/costs'),
};
