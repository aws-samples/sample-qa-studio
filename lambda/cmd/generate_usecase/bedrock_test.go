package main

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/bedrockruntime"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
)

// BedrockClientInterface defines the interface for Bedrock client operations
type BedrockClientInterface interface {
	InvokeModel(ctx context.Context, params *bedrockruntime.InvokeModelInput, optFns ...func(*bedrockruntime.Options)) (*bedrockruntime.InvokeModelOutput, error)
}

// MockBedrockClientInterface is a mock implementation for testing
type MockBedrockClientInterface struct {
	mock.Mock
}

func (m *MockBedrockClientInterface) InvokeModel(ctx context.Context, params *bedrockruntime.InvokeModelInput, optFns ...func(*bedrockruntime.Options)) (*bedrockruntime.InvokeModelOutput, error) {
	args := m.Called(ctx, params)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*bedrockruntime.InvokeModelOutput), args.Error(1)
}

func TestBedrockServiceInvokeBedrock(t *testing.T) {
	t.Run("successful invocation with valid response", func(t *testing.T) {
		mockClient := &MockBedrockClientInterface{}
		service := &bedrockService{
			client:         mockClient,
			modelID:        "anthropic.claude-3-5-sonnet-20241022-v2:0",
			retryConfig:    DefaultRetryConfig(),
			circuitBreaker: NewCircuitBreaker(),
		}

		// Create a valid Bedrock response
		validJSON := `{
			"exportVersion": "1.0",
			"exportedAt": "2025-01-09T10:00:00Z",
			"usecase": {
				"name": "Test Login Flow",
				"description": "Generated from user journey: User logs in",
				"starting_url": "https://example.com/login",
				"active": true,
				"headless": false,
				"tags": []
			},
			"steps": [
				{
					"sort": 1,
					"instruction": "Navigate to login page",
					"step_type": "navigation",
					"secret_key": "",
					"capture_variable": "",
					"validation_type": "",
					"validation_operator": "",
					"validation_value": "",
					"assertion_variable": "",
					"value_step": "",
					"value_type": ""
				}
			],
			"variables": [],
			"secrets": [],
			"hooks": null
		}`

		bedrockResponse := &bedrockruntime.InvokeModelOutput{
			Body: []byte(`{
				"content": [
					{
						"text": "` + validJSON + `"
					}
				]
			}`),
		}

		mockClient.On("InvokeModel", mock.Anything, mock.MatchedBy(func(input *bedrockruntime.InvokeModelInput) bool {
			return *input.ModelId == "anthropic.claude-3-5-sonnet-20241022-v2:0"
		})).Return(bedrockResponse, nil)

		request := GenerateUsecaseRequest{
			Title:       "Test Login Flow",
			StartingURL: "https://example.com/login",
			UserJourney: "User navigates to login page and enters credentials",
		}

		result, err := service.invokeBedrock(context.Background(), request)

		assert.NoError(t, err)
		assert.NotNil(t, result)
		assert.Contains(t, result.GeneratedJSON, "exportVersion")
		assert.Contains(t, result.GeneratedJSON, "Test Login Flow")
		assert.Equal(t, 0.9, result.Confidence)
		mockClient.AssertExpectations(t)
	})

	t.Run("handles Bedrock API error", func(t *testing.T) {
		mockClient := &MockBedrockClientInterface{}
		service := &bedrockService{
			client:         mockClient,
			modelID:        "test-model",
			retryConfig:    DefaultRetryConfig(),
			circuitBreaker: NewCircuitBreaker(),
		}

		bedrockError := errors.New("bedrock service error")
		mockClient.On("InvokeModel", mock.Anything, mock.Anything).Return(nil, bedrockError)

		request := GenerateUsecaseRequest{
			Title:       "Test Case",
			StartingURL: "https://example.com",
			UserJourney: "User performs actions on the website",
		}

		result, err := service.invokeBedrock(context.Background(), request)

		assert.Error(t, err)
		assert.Nil(t, result)
		assert.Contains(t, err.Error(), "bedrock invocation failed")
		mockClient.AssertExpectations(t)
	})

	t.Run("handles invalid response format", func(t *testing.T) {
		mockClient := &MockBedrockClientInterface{}
		service := &bedrockService{
			client:         mockClient,
			modelID:        "test-model",
			retryConfig:    DefaultRetryConfig(),
			circuitBreaker: NewCircuitBreaker(),
		}

		// Invalid response format
		bedrockResponse := &bedrockruntime.InvokeModelOutput{
			Body: []byte(`{"invalid": "format"}`),
		}

		mockClient.On("InvokeModel", mock.Anything, mock.Anything).Return(bedrockResponse, nil)

		request := GenerateUsecaseRequest{
			Title:       "Test Case",
			StartingURL: "https://example.com",
			UserJourney: "User performs actions on the website",
		}

		result, err := service.invokeBedrock(context.Background(), request)

		assert.Error(t, err)
		assert.Nil(t, result)
		assert.Contains(t, err.Error(), "invalid response format")
		mockClient.AssertExpectations(t)
	})

	t.Run("handles malformed JSON response", func(t *testing.T) {
		mockClient := &MockBedrockClientInterface{}
		service := &bedrockService{
			client:         mockClient,
			modelID:        "test-model",
			retryConfig:    DefaultRetryConfig(),
			circuitBreaker: NewCircuitBreaker(),
		}

		// Malformed JSON in response body
		bedrockResponse := &bedrockruntime.InvokeModelOutput{
			Body: []byte(`invalid json`),
		}

		mockClient.On("InvokeModel", mock.Anything, mock.Anything).Return(bedrockResponse, nil)

		request := GenerateUsecaseRequest{
			Title:       "Test Case",
			StartingURL: "https://example.com",
			UserJourney: "User performs actions on the website",
		}

		result, err := service.invokeBedrock(context.Background(), request)

		assert.Error(t, err)
		assert.Nil(t, result)
		assert.Contains(t, err.Error(), "failed to parse bedrock response")
		mockClient.AssertExpectations(t)
	})

	t.Run("handles empty content array", func(t *testing.T) {
		mockClient := &MockBedrockClientInterface{}
		service := &bedrockService{
			client:         mockClient,
			modelID:        "test-model",
			retryConfig:    DefaultRetryConfig(),
			circuitBreaker: NewCircuitBreaker(),
		}

		// Empty content array
		bedrockResponse := &bedrockruntime.InvokeModelOutput{
			Body: []byte(`{"content": []}`),
		}

		mockClient.On("InvokeModel", mock.Anything, mock.Anything).Return(bedrockResponse, nil)

		request := GenerateUsecaseRequest{
			Title:       "Test Case",
			StartingURL: "https://example.com",
			UserJourney: "User performs actions on the website",
		}

		result, err := service.invokeBedrock(context.Background(), request)

		assert.Error(t, err)
		assert.Nil(t, result)
		assert.Contains(t, err.Error(), "invalid response format")
		mockClient.AssertExpectations(t)
	})

	t.Run("validates request body structure", func(t *testing.T) {
		mockClient := &MockBedrockClientInterface{}
		service := &bedrockService{
			client:         mockClient,
			modelID:        "anthropic.claude-3-5-sonnet-20241022-v2:0",
			retryConfig:    DefaultRetryConfig(),
			circuitBreaker: NewCircuitBreaker(),
		}

		// Capture the request body to validate its structure
		var capturedInput *bedrockruntime.InvokeModelInput
		mockClient.On("InvokeModel", mock.Anything, mock.Anything).Run(func(args mock.Arguments) {
			capturedInput = args.Get(1).(*bedrockruntime.InvokeModelInput)
		}).Return(&bedrockruntime.InvokeModelOutput{
			Body: []byte(`{"content": [{"text": "{}"}]}`),
		}, nil)

		request := GenerateUsecaseRequest{
			Title:       "Test Case",
			StartingURL: "https://example.com",
			UserJourney: "User performs actions",
		}

		_, err := service.invokeBedrock(context.Background(), request)

		assert.NoError(t, err)
		assert.NotNil(t, capturedInput)
		assert.Equal(t, "anthropic.claude-3-5-sonnet-20241022-v2:0", *capturedInput.ModelId)
		assert.Equal(t, "application/json", *capturedInput.ContentType)
		assert.Equal(t, "application/json", *capturedInput.Accept)

		// Validate request body structure
		var requestBody map[string]interface{}
		err = json.Unmarshal(capturedInput.Body, &requestBody)
		assert.NoError(t, err)
		assert.Equal(t, "bedrock-2023-05-31", requestBody["anthropic_version"])
		assert.Equal(t, float64(4096), requestBody["max_tokens"])
		assert.Equal(t, 0.1, requestBody["temperature"])
		assert.Equal(t, 0.9, requestBody["top_p"])

		messages, ok := requestBody["messages"].([]interface{})
		assert.True(t, ok)
		assert.Len(t, messages, 1)

		message, ok := messages[0].(map[string]interface{})
		assert.True(t, ok)
		assert.Equal(t, "user", message["role"])
		assert.Contains(t, message["content"], request.Title)
		assert.Contains(t, message["content"], request.StartingURL)
		assert.Contains(t, message["content"], request.UserJourney)

		mockClient.AssertExpectations(t)
	})
}

func TestBedrockServiceWithCircuitBreaker(t *testing.T) {
	t.Run("circuit breaker prevents calls when open", func(t *testing.T) {
		mockClient := &MockBedrockClientInterface{}
		cb := NewCircuitBreaker()
		cb.maxFailures = 1 // Set low threshold for testing

		service := &bedrockService{
			client:         mockClient,
			modelID:        "test-model",
			retryConfig:    DefaultRetryConfig(),
			circuitBreaker: cb,
		}

		// Force circuit breaker to open
		cb.OnFailure()

		request := GenerateUsecaseRequest{
			Title:       "Test Case",
			StartingURL: "https://example.com",
			UserJourney: "User performs actions on the website",
		}

		result, err := service.GenerateUsecase(context.Background(), request)

		assert.Error(t, err)
		assert.Nil(t, result)
		assert.Contains(t, err.Error(), "circuit breaker")
		// Should not call the mock client
		mockClient.AssertNotCalled(t, "InvokeModel")
	})

	t.Run("circuit breaker allows calls when closed", func(t *testing.T) {
		mockClient := &MockBedrockClientInterface{}
		cb := NewCircuitBreaker()

		service := &bedrockService{
			client:         mockClient,
			modelID:        "test-model",
			retryConfig:    DefaultRetryConfig(),
			circuitBreaker: cb,
		}

		bedrockResponse := &bedrockruntime.InvokeModelOutput{
			Body: []byte(`{"content": [{"text": "{}"}]}`),
		}

		mockClient.On("InvokeModel", mock.Anything, mock.Anything).Return(bedrockResponse, nil)

		request := GenerateUsecaseRequest{
			Title:       "Test Case",
			StartingURL: "https://example.com",
			UserJourney: "User performs actions on the website",
		}

		result, err := service.GenerateUsecase(context.Background(), request)

		assert.NoError(t, err)
		assert.NotNil(t, result)
		mockClient.AssertExpectations(t)
	})
}

func TestBedrockServiceContextCancellation(t *testing.T) {
	t.Run("handles context cancellation during retry", func(t *testing.T) {
		mockClient := &MockBedrockClientInterface{}
		service := &bedrockService{
			client:         mockClient,
			modelID:        "test-model",
			retryConfig:    &RetryConfig{MaxRetries: 3, BaseDelay: 100 * time.Millisecond, MaxDelay: 1 * time.Second, BackoffFactor: 2.0},
			circuitBreaker: NewCircuitBreaker(),
		}

		// Mock retryable error
		retryableError := errors.New("throttling exception")
		mockClient.On("InvokeModel", mock.Anything, mock.Anything).Return(nil, retryableError)

		// Create context that will be cancelled
		ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
		defer cancel()

		request := GenerateUsecaseRequest{
			Title:       "Test Case",
			StartingURL: "https://example.com",
			UserJourney: "User performs actions on the website",
		}

		result, err := service.GenerateUsecase(ctx, request)

		assert.Error(t, err)
		assert.Nil(t, result)
		assert.Contains(t, err.Error(), "context")
	})

	t.Run("handles context cancellation during backoff", func(t *testing.T) {
		mockClient := &MockBedrockClientInterface{}
		service := &bedrockService{
			client:         mockClient,
			modelID:        "test-model",
			retryConfig:    &RetryConfig{MaxRetries: 3, BaseDelay: 200 * time.Millisecond, MaxDelay: 1 * time.Second, BackoffFactor: 2.0},
			circuitBreaker: NewCircuitBreaker(),
		}

		// Mock retryable error on first call
		retryableError := errors.New("service unavailable")
		mockClient.On("InvokeModel", mock.Anything, mock.Anything).Return(nil, retryableError).Once()

		// Create context that will be cancelled during backoff
		ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
		defer cancel()

		request := GenerateUsecaseRequest{
			Title:       "Test Case",
			StartingURL: "https://example.com",
			UserJourney: "User performs actions on the website",
		}

		result, err := service.GenerateUsecase(ctx, request)

		assert.Error(t, err)
		assert.Nil(t, result)
		assert.Contains(t, err.Error(), "context cancelled during retry backoff")
	})
}

func TestPromptGeneration(t *testing.T) {
	service := &bedrockService{}

	t.Run("prompt contains all required elements", func(t *testing.T) {
		request := GenerateUsecaseRequest{
			Title:       "Login Test with Special Characters: \"quotes\" & symbols",
			StartingURL: "https://example.com/login?param=value",
			UserJourney: "User navigates to login page, enters \"email@example.com\" and password, clicks login button",
		}

		prompt := service.createPrompt(request)

		// Check that all input data is included
		assert.Contains(t, prompt, request.Title)
		assert.Contains(t, prompt, request.StartingURL)
		assert.Contains(t, prompt, request.UserJourney)

		// Check that prompt contains schema requirements
		assert.Contains(t, prompt, "exportVersion")
		assert.Contains(t, prompt, "exportedAt")
		assert.Contains(t, prompt, "usecase")
		assert.Contains(t, prompt, "steps")
		assert.Contains(t, prompt, "variables")
		assert.Contains(t, prompt, "secrets")
		assert.Contains(t, prompt, "hooks")

		// Check step type requirements
		assert.Contains(t, prompt, "navigation")
		assert.Contains(t, prompt, "validation")
		assert.Contains(t, prompt, "secret")
		assert.Contains(t, prompt, "retrieve_value")

		// Check validation operator requirements
		assert.Contains(t, prompt, "equals")
		assert.Contains(t, prompt, "contains")
		assert.Contains(t, prompt, "not_equals")
		assert.Contains(t, prompt, "greater_than")
		assert.Contains(t, prompt, "less_than")

		// Check that quotes are properly escaped in the prompt
		assert.Contains(t, prompt, `\"quotes\"`)
		assert.Contains(t, prompt, `\"email@example.com\"`)
	})

	t.Run("prompt includes current timestamp", func(t *testing.T) {
		request := GenerateUsecaseRequest{
			Title:       "Test Case",
			StartingURL: "https://example.com",
			UserJourney: "User performs actions",
		}

		prompt := service.createPrompt(request)

		// Should contain a timestamp in RFC3339 format
		assert.Contains(t, prompt, "2025-01-09T")
		assert.Contains(t, prompt, "Z")
	})
}

func TestJSONExtraction(t *testing.T) {
	service := &bedrockService{}

	t.Run("extracts JSON from complex response", func(t *testing.T) {
		complexResponse := `
Here is the generated test case for your user journey:

` + "```json" + `
{
  "exportVersion": "1.0",
  "exportedAt": "2025-01-09T10:00:00Z",
  "usecase": {
    "name": "Complex Test Case",
    "description": "A test case with nested objects and arrays",
    "starting_url": "https://example.com",
    "active": true,
    "headless": false,
    "tags": ["login", "authentication"]
  },
  "steps": [
    {
      "sort": 1,
      "instruction": "Navigate to login page",
      "step_type": "navigation",
      "secret_key": "",
      "capture_variable": "",
      "validation_type": "",
      "validation_operator": "",
      "validation_value": "",
      "assertion_variable": "",
      "value_step": "",
      "value_type": ""
    },
    {
      "sort": 2,
      "instruction": "Verify login form is visible",
      "step_type": "validation",
      "secret_key": "",
      "capture_variable": "",
      "validation_type": "element_visible",
      "validation_operator": "equals",
      "validation_value": "true",
      "assertion_variable": "",
      "value_step": "",
      "value_type": ""
    }
  ],
  "variables": [],
  "secrets": [],
  "hooks": null
}
` + "```" + `

This test case covers the basic login flow as described in your user journey.
`

		result := service.extractJSON(complexResponse)

		// Should extract only the JSON part
		assert.True(t, strings.HasPrefix(result, "{"))
		assert.True(t, strings.HasSuffix(result, "}"))
		assert.Contains(t, result, "Complex Test Case")
		assert.Contains(t, result, "Navigate to login page")
		assert.Contains(t, result, "Verify login form is visible")

		// Should not contain markdown or explanatory text
		assert.NotContains(t, result, "```")
		assert.NotContains(t, result, "Here is the generated")
		assert.NotContains(t, result, "This test case covers")

		// Validate that extracted JSON is valid
		var jsonObj map[string]interface{}
		err := json.Unmarshal([]byte(result), &jsonObj)
		assert.NoError(t, err)
	})

	t.Run("handles unbalanced braces gracefully", func(t *testing.T) {
		unbalancedResponse := `{"key": "value", "nested": {"inner": "value"}`

		result := service.extractJSON(unbalancedResponse)

		// Should still return the input when no proper closing brace is found
		assert.Equal(t, unbalancedResponse, result)
	})

	t.Run("handles response with no JSON", func(t *testing.T) {
		noJSONResponse := "This response contains no JSON at all"

		result := service.extractJSON(noJSONResponse)

		// Should return the original text
		assert.Equal(t, noJSONResponse, result)
	})
}

// Benchmark tests for Bedrock service performance
func BenchmarkCreatePrompt(b *testing.B) {
	service := &bedrockService{}
	request := GenerateUsecaseRequest{
		Title:       "Performance Test Case",
		StartingURL: "https://example.com/test",
		UserJourney: "User navigates to login page, enters email and password, clicks login button, and should be redirected to dashboard page successfully",
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = service.createPrompt(request)
	}
}

func BenchmarkExtractJSONComplex(b *testing.B) {
	service := &bedrockService{}
	complexJSON := `Here is some text ` + "```json" + `{"exportVersion": "1.0", "usecase": {"name": "test", "description": "complex test case with many fields and nested objects", "starting_url": "https://example.com", "active": true, "headless": false, "tags": ["tag1", "tag2", "tag3"]}, "steps": [{"sort": 1, "instruction": "Navigate to page", "step_type": "navigation"}, {"sort": 2, "instruction": "Click button", "step_type": "navigation"}, {"sort": 3, "instruction": "Verify result", "step_type": "validation"}], "variables": [], "secrets": [], "hooks": null}` + "```" + ` and more text`

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = service.extractJSON(complexJSON)
	}
}
