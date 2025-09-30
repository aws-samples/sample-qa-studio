import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { wizardApi } from '../api';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock Auth module
vi.mock('@aws-amplify/auth', () => ({
  fetchAuthSession: vi.fn().mockResolvedValue({
    tokens: {
      idToken: {
        toString: () => 'mock-jwt-token'
      }
    }
  })
}));

describe('Wizard API', () => {
  const mockApiUrl = 'https://api.example.com';
  
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock environment variable
    vi.stubEnv('VITE_API_URL', mockApiUrl);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  describe('generateUsecase', () => {
    const validRequest = {
      title: 'Test Login Flow',
      startingUrl: 'https://example.com/login',
      userJourney: 'User navigates to login page, enters email and password, clicks login button, and should be redirected to dashboard page successfully'
    };

    it('makes successful API call with correct parameters', async () => {
      const mockResponse = {
        success: true,
        usecaseData: JSON.stringify({
          exportVersion: '1.0',
          usecase: { name: 'Test', description: 'Test case', starting_url: 'https://example.com', active: true, headless: false, region: 'us-east-1', tags: [] },
          steps: [],
          variables: [],
          secrets: [],
          hooks: null
        }),
        message: 'Use case generated successfully'
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockResponse)
      });

      const result = await wizardApi.generateUsecase(validRequest);

      expect(mockFetch).toHaveBeenCalledWith(
        `${mockApiUrl}/generate-usecase`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer mock-jwt-token'
          },
          body: JSON.stringify({
            title: validRequest.title,
            startingUrl: validRequest.startingUrl,
            userJourney: validRequest.userJourney
          })
        }
      );

      expect(result).toEqual(mockResponse);
    });

    it('handles validation errors correctly', async () => {
      const mockErrorResponse = {
        success: false,
        message: 'Request validation failed',
        error: 'Title is required',
        code: 'VALIDATION_ERROR',
        details: {
          validationErrors: [
            { field: 'title', message: 'Title is required', code: 'REQUIRED_FIELD' }
          ]
        }
      };

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () => Promise.resolve(mockErrorResponse)
      });

      const result = await wizardApi.generateUsecase({
        title: '',
        startingUrl: validRequest.startingUrl,
        userJourney: validRequest.userJourney
      });

      expect(result).toEqual(mockErrorResponse);
    });

    it('handles Bedrock service errors', async () => {
      const mockErrorResponse = {
        success: false,
        message: 'AI service is currently busy. Please try again in a moment',
        error: 'Rate limit exceeded',
        code: 'RATE_LIMIT_EXCEEDED'
      };

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 502,
        json: () => Promise.resolve(mockErrorResponse)
      });

      const result = await wizardApi.generateUsecase(validRequest);

      expect(result).toEqual(mockErrorResponse);
    });

    it('handles authentication errors', async () => {
      const mockErrorResponse = {
        success: false,
        message: 'Authentication failed',
        error: 'Invalid or expired authentication token',
        code: 'AUTH_FAILED'
      };

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: () => Promise.resolve(mockErrorResponse)
      });

      const result = await wizardApi.generateUsecase(validRequest);

      expect(result).toEqual(mockErrorResponse);
    });

    it('handles network errors', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      await expect(wizardApi.generateUsecase(validRequest)).rejects.toThrow('Network error');
    });

    it('handles timeout errors', async () => {
      // Mock a timeout scenario
      mockFetch.mockImplementationOnce(() => 
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Request timeout')), 100)
        )
      );

      await expect(wizardApi.generateUsecase(validRequest)).rejects.toThrow('Request timeout');
    });

    it('validates request parameters', async () => {
      // Test with missing required fields
      const invalidRequest = {
        title: '',
        startingUrl: '',
        userJourney: ''
      };

      const mockErrorResponse = {
        success: false,
        message: 'Request validation failed',
        error: 'Multiple validation errors',
        code: 'VALIDATION_ERROR'
      };

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () => Promise.resolve(mockErrorResponse)
      });

      const result = await wizardApi.generateUsecase(invalidRequest);

      expect(result.success).toBe(false);
      expect(result.code).toBe('VALIDATION_ERROR');
    });

    it('handles malformed JSON responses', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.reject(new Error('Invalid JSON'))
      });

      await expect(wizardApi.generateUsecase(validRequest)).rejects.toThrow('Invalid JSON');
    });

    it('includes proper headers in request', async () => {
      const mockResponse = {
        success: true,
        usecaseData: '{}',
        message: 'Success'
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockResponse)
      });

      await wizardApi.generateUsecase(validRequest);

      const fetchCall = mockFetch.mock.calls[0];
      const [url, options] = fetchCall;

      expect(url).toBe(`${mockApiUrl}/generate-usecase`);
      expect(options.method).toBe('POST');
      expect(options.headers['Content-Type']).toBe('application/json');
      expect(options.headers['Authorization']).toBe('Bearer mock-jwt-token');
    });

    it('properly serializes request body', async () => {
      const mockResponse = {
        success: true,
        usecaseData: '{}',
        message: 'Success'
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockResponse)
      });

      await wizardApi.generateUsecase(validRequest);

      const fetchCall = mockFetch.mock.calls[0];
      const [, options] = fetchCall;
      const requestBody = JSON.parse(options.body);

      expect(requestBody).toEqual({
        title: validRequest.title,
        startingUrl: validRequest.startingUrl,
        userJourney: validRequest.userJourney
      });
    });
  });

  describe('Error Handling', () => {
    const validRequest = {
      title: 'Test Case',
      startingUrl: 'https://example.com',
      userJourney: 'User performs actions on the website successfully'
    };

    it('handles 500 internal server errors', async () => {
      const mockErrorResponse = {
        success: false,
        message: 'Internal server error',
        error: 'An unexpected error occurred',
        code: 'INTERNAL_ERROR'
      };

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.resolve(mockErrorResponse)
      });

      const result = await wizardApi.generateUsecase(validRequest);

      expect(result.success).toBe(false);
      expect(result.code).toBe('INTERNAL_ERROR');
    });

    it('handles 503 service unavailable errors', async () => {
      const mockErrorResponse = {
        success: false,
        message: 'Service temporarily unavailable',
        error: 'The service is currently down for maintenance',
        code: 'SERVICE_UNAVAILABLE'
      };

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 503,
        json: () => Promise.resolve(mockErrorResponse)
      });

      const result = await wizardApi.generateUsecase(validRequest);

      expect(result.success).toBe(false);
      expect(result.code).toBe('SERVICE_UNAVAILABLE');
    });

    it('handles responses without error details', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () => Promise.resolve({})
      });

      const result = await wizardApi.generateUsecase(validRequest);

      expect(result.success).toBe(false);
    });

    it('handles empty response body', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.resolve(null)
      });

      await expect(wizardApi.generateUsecase(validRequest)).rejects.toThrow();
    });
  });

  describe('Authentication Integration', () => {
    const validRequest = {
      title: 'Test Case',
      startingUrl: 'https://example.com',
      userJourney: 'User performs actions successfully'
    };

    it('includes JWT token in Authorization header', async () => {
      const mockResponse = {
        success: true,
        usecaseData: '{}',
        message: 'Success'
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockResponse)
      });

      await wizardApi.generateUsecase(validRequest);

      const fetchCall = mockFetch.mock.calls[0];
      const [, options] = fetchCall;

      expect(options.headers['Authorization']).toBe('Bearer mock-jwt-token');
    });

    it('handles missing authentication token', async () => {
      // Mock Auth to return no token
      const { fetchAuthSession } = await import('@aws-amplify/auth');
      vi.mocked(fetchAuthSession).mockResolvedValueOnce({
        tokens: undefined
      } as any);

      await expect(wizardApi.generateUsecase(validRequest)).rejects.toThrow();
    });
  });

  describe('Response Validation', () => {
    const validRequest = {
      title: 'Test Case',
      startingUrl: 'https://example.com',
      userJourney: 'User performs actions successfully'
    };

    it('validates successful response structure', async () => {
      const mockResponse = {
        success: true,
        usecaseData: JSON.stringify({
          exportVersion: '1.0',
          usecase: { name: 'Test', description: 'Test', starting_url: 'https://example.com', active: true, headless: false, region: 'us-east-1', tags: [] },
          steps: [],
          variables: [],
          secrets: [],
          hooks: null
        }),
        message: 'Success'
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockResponse)
      });

      const result = await wizardApi.generateUsecase(validRequest);

      expect(result.success).toBe(true);
      expect(result.usecaseData).toBeDefined();
      expect(result.message).toBeDefined();
      
      // Validate that usecaseData is valid JSON
      expect(() => JSON.parse(result.usecaseData)).not.toThrow();
    });

    it('validates error response structure', async () => {
      const mockErrorResponse = {
        success: false,
        message: 'Validation failed',
        error: 'Invalid input',
        code: 'VALIDATION_ERROR'
      };

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () => Promise.resolve(mockErrorResponse)
      });

      const result = await wizardApi.generateUsecase(validRequest);

      expect(result.success).toBe(false);
      expect(result.message).toBeDefined();
      expect(result.error).toBeDefined();
      expect(result.code).toBeDefined();
    });
  });

  describe('Performance', () => {
    const validRequest = {
      title: 'Performance Test Case',
      startingUrl: 'https://example.com',
      userJourney: 'User performs multiple complex actions on the website including navigation, form filling, validation, and completion of the entire workflow successfully'
    };

    it('handles large request payloads efficiently', async () => {
      const largeRequest = {
        ...validRequest,
        userJourney: 'A'.repeat(2000) // Maximum allowed length
      };

      const mockResponse = {
        success: true,
        usecaseData: '{}',
        message: 'Success'
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockResponse)
      });

      const startTime = performance.now();
      const result = await wizardApi.generateUsecase(largeRequest);
      const endTime = performance.now();

      expect(result.success).toBe(true);
      expect(endTime - startTime).toBeLessThan(1000); // Should complete quickly
    });

    it('handles large response payloads efficiently', async () => {
      // Mock a large response with many steps
      const largeUsecaseData = {
        exportVersion: '1.0',
        usecase: { name: 'Large Test', description: 'Test', starting_url: 'https://example.com', active: true, headless: false, region: 'us-east-1', tags: [] },
        steps: Array.from({ length: 100 }, (_, i) => ({
          sort: i + 1,
          instruction: `Step ${i + 1}`,
          step_type: 'navigation',
          secret_key: '',
          capture_variable: '',
          validation_type: '',
          validation_operator: '',
          validation_value: '',
          assertion_variable: '',
          value_step: '',
          value_type: ''
        })),
        variables: [],
        secrets: [],
        hooks: null
      };

      const mockResponse = {
        success: true,
        usecaseData: JSON.stringify(largeUsecaseData),
        message: 'Success'
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockResponse)
      });

      const startTime = performance.now();
      const result = await wizardApi.generateUsecase(validRequest);
      const endTime = performance.now();

      expect(result.success).toBe(true);
      expect(endTime - startTime).toBeLessThan(1000); // Should handle large responses quickly
      
      const parsedData = JSON.parse(result.usecaseData);
      expect(parsedData.steps).toHaveLength(100);
    });
  });
});