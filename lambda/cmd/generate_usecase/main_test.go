package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/bedrockruntime"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
)

// MockBedrockService is a mock implementation of BedrockService for testing
type MockBedrockService struct {
	mock.Mock
}

func (m *MockBedrockService) GenerateUsecase(ctx context.Context, request GenerateUsecaseRequest) (*BedrockResponse, error) {
	args := m.Called(ctx, request)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*BedrockResponse), args.Error(1)
}

// MockBedrockClient is a mock implementation of Bedrock client for testing
type MockBedrockClient struct {
	mock.Mock
}

func (m *MockBedrockClient) InvokeModel(ctx context.Context, params *bedrockruntime.InvokeModelInput, optFns ...func(*bedrockruntime.Options)) (*bedrockruntime.InvokeModelOutput, error) {
	args := m.Called(ctx, params)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*bedrockruntime.InvokeModelOutput), args.Error(1)
}

func TestValidateRequest(t *testing.T) {
	tests := []struct {
		name        string
		request     GenerateUsecaseRequest
		expectError bool
		errorField  string
	}{
		{
			name: "valid request",
			request: GenerateUsecaseRequest{
				Title:       "Valid Test Case",
				StartingURL: "https://example.com",
				UserJourney: "User navigates to login page, enters email and password, clicks login button, and should be redirected to dashboard page successfully",
			},
			expectError: false,
		},
		{
			name: "empty title",
			request: GenerateUsecaseRequest{
				Title:       "",
				StartingURL: "https://example.com",
				UserJourney: "User navigates to login page, enters email and password, clicks login button, and should be redirected to dashboard page successfully",
			},
			expectError: true,
			errorField:  "title",
		},
		{
			name: "invalid URL",
			request: GenerateUsecaseRequest{
				Title:       "Valid Test Case",
				StartingURL: "invalid-url",
				UserJourney: "User navigates to login page, enters email and password, clicks login button, and should be redirected to dashboard page successfully",
			},
			expectError: true,
			errorField:  "startingUrl",
		},
		{
			name: "empty user journey",
			request: GenerateUsecaseRequest{
				Title:       "Valid Test Case",
				StartingURL: "https://example.com",
				UserJourney: "",
			},
			expectError: true,
			errorField:  "userJourney",
		},
		{
			name: "user journey too short",
			request: GenerateUsecaseRequest{
				Title:       "Valid Test Case",
				StartingURL: "https://example.com",
				UserJourney: "Short journey",
			},
			expectError: true,
			errorField:  "userJourney",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateRequest(&tt.request)

			if tt.expectError {
				assert.Error(t, err)
				if tt.errorField != "" {
					validationErrors, ok := err.(*ValidationErrors)
					assert.True(t, ok, "Expected ValidationErrors type")
					if ok {
						found := false
						for _, validationErr := range validationErrors.Errors {
							if validationErr.Field == tt.errorField {
								found = true
								break
							}
						}
						assert.True(t, found, "Expected error for field %s", tt.errorField)
					}
				}
			} else {
				assert.NoError(t, err)
			}
		})
	}
}

func TestCircuitBreaker(t *testing.T) {
	t.Run("initial state is closed", func(t *testing.T) {
		cb := NewCircuitBreaker()
		assert.True(t, cb.CanExecute())
		assert.Equal(t, CircuitClosed, cb.GetState())
	})

	t.Run("opens after max failures", func(t *testing.T) {
		cb := NewCircuitBreaker()
		cb.maxFailures = 3

		// Record failures
		for i := 0; i < 3; i++ {
			cb.OnFailure()
		}

		assert.False(t, cb.CanExecute())
		assert.Equal(t, CircuitOpen, cb.GetState())
	})

	t.Run("transitions to half-open after timeout", func(t *testing.T) {
		cb := NewCircuitBreaker()
		cb.maxFailures = 2
		cb.resetTimeout = 100 * time.Millisecond

		// Force circuit to open
		cb.OnFailure()
		cb.OnFailure()
		assert.Equal(t, CircuitOpen, cb.GetState())

		// Wait for timeout
		time.Sleep(150 * time.Millisecond)

		// Should transition to half-open
		assert.True(t, cb.CanExecute())
		assert.Equal(t, CircuitHalfOpen, cb.GetState())
	})

	t.Run("closes after successful executions in half-open", func(t *testing.T) {
		cb := NewCircuitBreaker()
		cb.state = CircuitHalfOpen

		// Record 3 successes
		for i := 0; i < 3; i++ {
			cb.OnSuccess()
		}

		assert.Equal(t, CircuitClosed, cb.GetState())
	})
}

func TestBedrockServiceRetryLogic(t *testing.T) {
	t.Run("succeeds on first attempt", func(t *testing.T) {
		mockClient := &MockBedrockClient{}
		service := &bedrockService{
			client:         mockClient,
			modelID:        "test-model",
			retryConfig:    DefaultRetryConfig(),
			circuitBreaker: NewCircuitBreaker(),
		}

		// Mock successful response
		mockResponse := &bedrockruntime.InvokeModelOutput{
			Body: []byte(`{"content": [{"text": "{\"exportVersion\": \"1.0\", \"exportedAt\": \"2025-01-09T10:00:00Z\", \"usecase\": {\"name\": \"Test\", \"description\": \"Test case\", \"starting_url\": \"https://example.com\", \"active\": true, \"headless\": false, \"tags\": []}, \"steps\": [{\"sort\": 1, \"instruction\": \"Navigate to page\", \"step_type\": \"navigation\", \"secret_key\": \"\", \"capture_variable\": \"\", \"validation_type\": \"\", \"validation_operator\": \"\", \"validation_value\": \"\", \"assertion_variable\": \"\", \"value_step\": \"\", \"value_type\": \"\"}], \"variables\": [], \"secrets\": [], \"hooks\": null}"}]}`)},
		}

		mockClient.On("InvokeModel", mock.Anything, mock.Anything).Return(mockResponse, nil).Once()

		request := GenerateUsecaseRequest{
			Title:       "Test Case",
			StartingURL: "https://example.com",
			UserJourney: "User clicks button and navigates to page",
		}

		result, err := service.GenerateUsecase(context.Background(), request)

		assert.NoError(t, err)
		assert.NotNil(t, result)
		assert.NotEmpty(t, result.GeneratedJSON)
		mockClient.AssertExpectations(t)
	})

	t.Run("retries on retryable error", func(t *testing.T) {
		mockClient := &MockBedrockClient{}
		service := &bedrockService{
			client:      mockClient,
			modelID:     "test-model",
			retryConfig: &RetryConfig{MaxRetries: 2, BaseDelay: 1 * time.Millisecond, MaxDelay: 10 * time.Millisecond, BackoffFactor: 2.0},
			circuitBreaker: NewCircuitBreaker(),
		}

		// Mock retryable error followed by success
		retryableError := errors.New("throttling exception")
		mockResponse := &bedrockruntime.InvokeModelOutput{
			Body: []byte(`{"content": [{"text": "{\"exportVersion\": \"1.0\", \"exportedAt\": \"2025-01-09T10:00:00Z\", \"usecase\": {\"name\": \"Test\", \"description\": \"Test case\", \"starting_url\": \"https://example.com\", \"active\": true, \"headless\": false, \"tags\": []}, \"steps\": [{\"sort\": 1, \"instruction\": \"Navigate to page\", \"step_type\": \"navigation\", \"secret_key\": \"\", \"capture_variable\": \"\", \"validation_type\": \"\", \"validation_operator\": \"\", \"validation_value\": \"\", \"assertion_variable\": \"\", \"value_step\": \"\", \"value_type\": \"\"}], \"variables\": [], \"secrets\": [], \"hooks\": null}"}]}`)},
		}

		mockClient.On("InvokeModel", mock.Anything, mock.Anything).Return(nil, retryableError).Once()
		mockClient.On("InvokeModel", mock.Anything, mock.Anything).Return(mockResponse, nil).Once()

		request := GenerateUsecaseRequest{
			Title:       "Test Case",
			StartingURL: "https://example.com",
			UserJourney: "User clicks button and navigates to page",
		}

		result, err := service.GenerateUsecase(context.Background(), request)

		assert.NoError(t, err)
		assert.NotNil(t, result)
		mockClient.AssertExpectations(t)
	})

	t.Run("fails after max retries", func(t *testing.T) {
		mockClient := &MockBedrockClient{}
		service := &bedrockService{
			client:      mockClient,
			modelID:     "test-model",
			retryConfig: &RetryConfig{MaxRetries: 1, BaseDelay: 1 * time.Millisecond, MaxDelay: 10 * time.Millisecond, BackoffFactor: 2.0},
			circuitBreaker: NewCircuitBreaker(),
		}

		// Mock persistent retryable error
		retryableError := errors.New("service unavailable")
		mockClient.On("InvokeModel", mock.Anything, mock.Anything).Return(nil, retryableError).Times(2)

		request := GenerateUsecaseRequest{
			Title:       "Test Case",
			StartingURL: "https://example.com",
			UserJourney: "User clicks button and navigates to page",
		}

		result, err := service.GenerateUsecase(context.Background(), request)

		assert.Error(t, err)
		assert.Nil(t, result)
		assert.Contains(t, err.Error(), "failed after")
		mockClient.AssertExpectations(t)
	})

	t.Run("fails immediately on non-retryable error", func(t *testing.T) {
		mockClient := &MockBedrockClient{}
		service := &bedrockService{
			client:         mockClient,
			modelID:        "test-model",
			retryConfig:    DefaultRetryConfig(),
			circuitBreaker: NewCircuitBreaker(),
		}

		// Mock non-retryable error
		nonRetryableError := errors.New("access denied")
		mockClient.On("InvokeModel", mock.Anything, mock.Anything).Return(nil, nonRetryableError).Once()

		request := GenerateUsecaseRequest{
			Title:       "Test Case",
			StartingURL: "https://example.com",
			UserJourney: "User clicks button and navigates to page",
		}

		result, err := service.GenerateUsecase(context.Background(), request)

		assert.Error(t, err)
		assert.Nil(t, result)
		assert.Contains(t, err.Error(), "non-retryable")
		mockClient.AssertExpectations(t)
	})
}

func TestIsRetryableError(t *testing.T) {
	service := &bedrockService{}

	tests := []struct {
		name      string
		error     error
		retryable bool
	}{
		{"throttling error", errors.New("throttling exception"), true},
		{"rate limit error", errors.New("rate limit exceeded"), true},
		{"timeout error", errors.New("request timeout"), true},
		{"service unavailable", errors.New("service unavailable"), true},
		{"internal server error", errors.New("internal server error"), true},
		{"502 error", errors.New("502 bad gateway"), true},
		{"access denied", errors.New("access denied"), false},
		{"unauthorized", errors.New("unauthorized"), false},
		{"bad request", errors.New("bad request"), false},
		{"400 error", errors.New("400 bad request"), false},
		{"unknown error", errors.New("unknown error"), true}, // Default to retryable
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := service.isRetryableError(tt.error)
			assert.Equal(t, tt.retryable, result)
		})
	}
}

func TestCalculateBackoffDelay(t *testing.T) {
	service := &bedrockService{
		retryConfig: &RetryConfig{
			BaseDelay:     1 * time.Second,
			MaxDelay:      30 * time.Second,
			BackoffFactor: 2.0,
			JitterEnabled: false, // Disable jitter for predictable testing
		},
	}

	tests := []struct {
		name     string
		attempt  int
		expected time.Duration
	}{
		{"first retry", 1, 1 * time.Second},
		{"second retry", 2, 2 * time.Second},
		{"third retry", 3, 4 * time.Second},
		{"max delay reached", 10, 30 * time.Second}, // Should be capped at MaxDelay
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := service.calculateBackoffDelay(tt.attempt)
			assert.Equal(t, tt.expected, result)
		})
	}
}

func TestCreatePrompt(t *testing.T) {
	service := &bedrockService{}

	request := GenerateUsecaseRequest{
		Title:       "Test Login Flow",
		StartingURL: "https://example.com/login",
		UserJourney: "User enters credentials and clicks login",
	}

	prompt := service.createPrompt(request)

	assert.Contains(t, prompt, request.Title)
	assert.Contains(t, prompt, request.StartingURL)
	assert.Contains(t, prompt, request.UserJourney)
	assert.Contains(t, prompt, "exportVersion")
	assert.Contains(t, prompt, "usecase")
	assert.Contains(t, prompt, "steps")
	assert.Contains(t, prompt, "navigation")
	assert.Contains(t, prompt, "validation")
}

func TestExtractJSON(t *testing.T) {
	service := &bedrockService{}

	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{
			name:     "clean JSON",
			input:    `{"key": "value"}`,
			expected: `{"key": "value"}`,
		},
		{
			name:     "JSON with markdown",
			input:    "```json\n{\"key\": \"value\"}\n```",
			expected: `{"key": "value"}`,
		},
		{
			name:     "JSON with extra text",
			input:    "Here is the JSON: {\"key\": \"value\"} and some more text",
			expected: `{"key": "value"}`,
		},
		{
			name:     "nested JSON",
			input:    `{"outer": {"inner": "value"}}`,
			expected: `{"outer": {"inner": "value"}}`,
		},
		{
			name:     "JSON with arrays",
			input:    `{"items": [{"id": 1}, {"id": 2}]}`,
			expected: `{"items": [{"id": 1}, {"id": 2}]}`,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := service.extractJSON(tt.input)
			assert.Equal(t, tt.expected, result)
		})
	}
}

func TestGetErrorCode(t *testing.T) {
	tests := []struct {
		name     string
		message  string
		expected string
	}{
		{"required field", "Title is required", "REQUIRED_FIELD"},
		{"max length", "Title must be 200 characters or less", "MAX_LENGTH_EXCEEDED"},
		{"min length", "Title must be at least 3 characters", "MIN_LENGTH_NOT_MET"},
		{"invalid format", "Invalid URL format", "INVALID_FORMAT"},
		{"invalid URL", "URL must start with http://", "INVALID_URL"},
		{"security violation", "Potential XSS content detected", "SECURITY_VIOLATION"},
		{"generic error", "Something went wrong", "VALIDATION_ERROR"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := getErrorCode(tt.message)
			assert.Equal(t, tt.expected, result)
		})
	}
}

func TestHandler(t *testing.T) {
	// Mock valid JWT token payload
	validJWTPayload := `{
		"sub": "test-user-id",
		"email": "test@example.com",
		"aud": "test-audience",
		"iss": "test-issuer",
		"exp": 9999999999
	}`

	t.Run("successful request", func(t *testing.T) {
		// Create a valid request
		requestBody := GenerateUsecaseRequest{
			Title:       "Test Login Flow",
			StartingURL: "https://example.com/login",
			UserJourney: "User navigates to login page, enters email and password, clicks login button, and should be redirected to dashboard page successfully",
		}

		bodyBytes, _ := json.Marshal(requestBody)

		request := events.APIGatewayProxyRequest{
			Body: string(bodyBytes),
			RequestContext: events.APIGatewayProxyRequestContext{
				RequestID: "test-request-id",
				Authorizer: map[string]interface{}{
					"claims": map[string]interface{}{
						"sub":   "test-user-id",
						"email": "test@example.com",
					},
				},
			},
		}

		// Note: This test would require mocking AWS services, which is complex
		// In a real scenario, you'd use dependency injection to mock the Bedrock service
		// For now, we'll test the request parsing and validation parts
		
		var req GenerateUsecaseRequest
		err := json.Unmarshal([]byte(request.Body), &req)
		assert.NoError(t, err)

		err = validateRequest(&req)
		assert.NoError(t, err)
	})

	t.Run("invalid JSON request", func(t *testing.T) {
		request := events.APIGatewayProxyRequest{
			Body: "invalid json",
			RequestContext: events.APIGatewayProxyRequestContext{
				RequestID: "test-request-id",
			},
		}

		response, err := handler(context.Background(), request)

		assert.NoError(t, err) // Lambda handler should not return error for business logic failures
		assert.Equal(t, 400, response.StatusCode)

		var errorResponse ErrorResponse
		err = json.Unmarshal([]byte(response.Body), &errorResponse)
		assert.NoError(t, err)
		assert.False(t, errorResponse.Success)
		assert.Contains(t, errorResponse.Message, "Invalid request format")
	})

	t.Run("validation error", func(t *testing.T) {
		requestBody := GenerateUsecaseRequest{
			Title:       "", // Invalid: empty title
			StartingURL: "https://example.com",
			UserJourney: "User clicks button and navigates to page successfully with proper actions",
		}

		bodyBytes, _ := json.Marshal(requestBody)

		request := events.APIGatewayProxyRequest{
			Body: string(bodyBytes),
			RequestContext: events.APIGatewayProxyRequestContext{
				RequestID: "test-request-id",
			},
		}

		response, err := handler(context.Background(), request)

		assert.NoError(t, err)
		assert.Equal(t, 400, response.StatusCode)

		var errorResponse ErrorResponse
		err = json.Unmarshal([]byte(response.Body), &errorResponse)
		assert.NoError(t, err)
		assert.False(t, errorResponse.Success)
		assert.Contains(t, errorResponse.Message, "validation failed")
	})
}

func TestCreateErrorResponse(t *testing.T) {
	response := createErrorResponse(400, "Test error", "Error details")

	assert.Equal(t, 400, response.StatusCode)
	assert.Contains(t, response.Headers, "Content-Type")
	assert.Equal(t, "application/json", response.Headers["Content-Type"])

	var errorResponse ErrorResponse
	err := json.Unmarshal([]byte(response.Body), &errorResponse)
	assert.NoError(t, err)
	assert.False(t, errorResponse.Success)
	assert.Equal(t, "Test error", errorResponse.Message)
	assert.Equal(t, "Error details", errorResponse.Error)
}

func TestCreateValidationErrorResponse(t *testing.T) {
	validationErrors := &ValidationErrors{
		Errors: []ValidationError{
			{Field: "title", Message: "Title is required", Code: "REQUIRED_FIELD"},
			{Field: "url", Message: "Invalid URL", Code: "INVALID_URL"},
		},
	}

	response := createValidationErrorResponse(validationErrors)

	assert.Equal(t, 400, response.StatusCode)

	var errorResponse ErrorResponse
	err := json.Unmarshal([]byte(response.Body), &errorResponse)
	assert.NoError(t, err)
	assert.False(t, errorResponse.Success)
	assert.Equal(t, "Request validation failed", errorResponse.Message)
	assert.Equal(t, "VALIDATION_ERROR", errorResponse.Code)
	assert.NotNil(t, errorResponse.Details)
}

func TestGetCORSHeaders(t *testing.T) {
	headers := getCORSHeaders()

	expectedHeaders := map[string]string{
		"Content-Type":                 "application/json",
		"Access-Control-Allow-Origin":  "*",
		"Access-Control-Allow-Methods": "POST, OPTIONS",
		"Access-Control-Allow-Headers": "Content-Type, Authorization",
	}

	for key, expectedValue := range expectedHeaders {
		assert.Equal(t, expectedValue, headers[key])
	}
}

func TestLogWithContext(t *testing.T) {
	logCtx := &LogContext{
		RequestID: "test-request-id",
		UserID:    "test-user-id",
		UserEmail: "test@example.com",
		Operation: "test-operation",
	}

	// This test just ensures the function doesn't panic
	// In a real scenario, you might want to capture log output
	assert.NotPanics(t, func() {
		logWithContext(logCtx, "INFO", "Test message")
		logWithContext(logCtx, "ERROR", "Test error with args: %s", "arg1")
	})
}

// Benchmark tests for performance validation
func BenchmarkValidateRequest(b *testing.B) {
	request := GenerateUsecaseRequest{
		Title:       "Performance Test Case",
		StartingURL: "https://example.com/test",
		UserJourney: "User navigates to login page, enters email and password, clicks login button, and should be redirected to dashboard page successfully",
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = validateRequest(&request)
	}
}

func BenchmarkExtractJSON(b *testing.B) {
	service := &bedrockService{}
	input := `Here is some text before the JSON: {"exportVersion": "1.0", "usecase": {"name": "test", "description": "test case"}, "steps": [{"sort": 1, "instruction": "test"}]} and some text after`

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = service.extractJSON(input)
	}
}

func BenchmarkCircuitBreakerCanExecute(b *testing.B) {
	cb := NewCircuitBreaker()

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = cb.CanExecute()
	}
}