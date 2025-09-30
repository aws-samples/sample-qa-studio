package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"os"
	"strings"
	"sync"
	"time"

	"lambda/user_journey"
	"lambda/utils"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/bedrockruntime"
)

// Request structure for generate usecase
type GenerateUsecaseRequest struct {
	Title       string `json:"title"`
	StartingURL string `json:"startingUrl"`
	UserJourney string `json:"userJourney"`
	Region      string `json:"region"`
}

// Response structure for generate usecase
type GenerateUsecaseResponse struct {
	Success     bool   `json:"success"`
	UsecaseData string `json:"usecaseData,omitempty"` // JSON string compatible with import_usecase
	Message     string `json:"message"`
	Error       string `json:"error,omitempty"`
}

// Bedrock service interface
type BedrockService interface {
	GenerateUsecase(ctx context.Context, request GenerateUsecaseRequest) (*BedrockResponse, error)
}

// Bedrock response structure
type BedrockResponse struct {
	GeneratedJSON string  `json:"generatedJson"`
	Confidence    float64 `json:"confidence"`
}

// CircuitBreakerState represents the state of the circuit breaker
type CircuitBreakerState int

const (
	CircuitClosed CircuitBreakerState = iota
	CircuitOpen
	CircuitHalfOpen
)

// CircuitBreaker implements the circuit breaker pattern for Bedrock calls
type CircuitBreaker struct {
	mutex           sync.RWMutex
	state           CircuitBreakerState
	failureCount    int
	successCount    int
	lastFailureTime time.Time
	timeout         time.Duration
	maxFailures     int
	resetTimeout    time.Duration
}

// NewCircuitBreaker creates a new circuit breaker
func NewCircuitBreaker() *CircuitBreaker {
	return &CircuitBreaker{
		state:        CircuitClosed,
		timeout:      30 * time.Second,
		maxFailures:  5,
		resetTimeout: 60 * time.Second,
	}
}

// CanExecute checks if the circuit breaker allows execution
func (cb *CircuitBreaker) CanExecute() bool {
	cb.mutex.RLock()
	defer cb.mutex.RUnlock()

	switch cb.state {
	case CircuitClosed:
		return true
	case CircuitOpen:
		return time.Since(cb.lastFailureTime) >= cb.resetTimeout
	case CircuitHalfOpen:
		return true
	default:
		return false
	}
}

// OnSuccess records a successful execution
func (cb *CircuitBreaker) OnSuccess() {
	cb.mutex.Lock()
	defer cb.mutex.Unlock()

	cb.failureCount = 0
	if cb.state == CircuitHalfOpen {
		cb.successCount++
		if cb.successCount >= 3 { // Require 3 successes to close
			cb.state = CircuitClosed
			cb.successCount = 0
		}
	}
}

// OnFailure records a failed execution
func (cb *CircuitBreaker) OnFailure() {
	cb.mutex.Lock()
	defer cb.mutex.Unlock()

	cb.failureCount++
	cb.lastFailureTime = time.Now()

	if cb.failureCount >= cb.maxFailures {
		cb.state = CircuitOpen
	} else if cb.state == CircuitHalfOpen {
		cb.state = CircuitOpen
	}
}

// GetState returns the current state of the circuit breaker
func (cb *CircuitBreaker) GetState() CircuitBreakerState {
	cb.mutex.RLock()
	defer cb.mutex.RUnlock()

	if cb.state == CircuitOpen && time.Since(cb.lastFailureTime) >= cb.resetTimeout {
		cb.mutex.RUnlock()
		cb.mutex.Lock()
		cb.state = CircuitHalfOpen
		cb.successCount = 0
		cb.mutex.Unlock()
		cb.mutex.RLock()
	}

	return cb.state
}

// Global circuit breaker instance
var globalCircuitBreaker = NewCircuitBreaker()

// RetryConfig holds configuration for retry logic
type RetryConfig struct {
	MaxRetries    int
	BaseDelay     time.Duration
	MaxDelay      time.Duration
	BackoffFactor float64
	JitterEnabled bool
}

// DefaultRetryConfig returns the default retry configuration
func DefaultRetryConfig() *RetryConfig {
	return &RetryConfig{
		MaxRetries:    3,
		BaseDelay:     1 * time.Second,
		MaxDelay:      30 * time.Second,
		BackoffFactor: 2.0,
		JitterEnabled: true,
	}
}

// Bedrock service implementation
type bedrockService struct {
	client         *bedrockruntime.Client
	modelID        string
	retryConfig    *RetryConfig
	circuitBreaker *CircuitBreaker
}

// NewBedrockService creates a new Bedrock service instance
func NewBedrockService(cfg aws.Config) BedrockService {
	client := bedrockruntime.NewFromConfig(cfg)
	modelID := os.Getenv("BEDROCK_MODEL_ID")
	if modelID == "" {
		modelID = "anthropic.claude-3-5-sonnet-20241022-v2:0" // Default model
	}

	return &bedrockService{
		client:         client,
		modelID:        modelID,
		retryConfig:    DefaultRetryConfig(),
		circuitBreaker: globalCircuitBreaker,
	}
}

// GenerateUsecase processes the user journey and generates a structured test case
func (b *bedrockService) GenerateUsecase(ctx context.Context, request GenerateUsecaseRequest) (*BedrockResponse, error) {
	// Check circuit breaker state
	if !b.circuitBreaker.CanExecute() {
		state := b.circuitBreaker.GetState()
		log.Printf("Circuit breaker is %v, rejecting request", state)
		return nil, fmt.Errorf("bedrock service is temporarily unavailable (circuit breaker %v)", state)
	}

	var lastErr error
	for attempt := 0; attempt <= b.retryConfig.MaxRetries; attempt++ {
		if attempt > 0 {
			// Calculate exponential backoff with jitter
			delay := b.calculateBackoffDelay(attempt)
			log.Printf("Retrying Bedrock call (attempt %d/%d) after %v", attempt+1, b.retryConfig.MaxRetries+1, delay)

			select {
			case <-time.After(delay):
				// Continue with retry
			case <-ctx.Done():
				return nil, fmt.Errorf("context cancelled during retry backoff: %v", ctx.Err())
			}
		}

		response, err := b.invokeBedrock(ctx, request)
		if err == nil {
			b.circuitBreaker.OnSuccess()
			log.Printf("Bedrock call succeeded on attempt %d", attempt+1)
			return response, nil
		}

		lastErr = err
		log.Printf("Bedrock call attempt %d failed: %v", attempt+1, err)

		// Check if error is retryable
		if !b.isRetryableError(err) {
			log.Printf("Non-retryable error encountered: %v", err)
			b.circuitBreaker.OnFailure()
			return nil, fmt.Errorf("bedrock call failed with non-retryable error: %v", err)
		}

		// Check context cancellation
		if ctx.Err() != nil {
			return nil, fmt.Errorf("context cancelled: %v", ctx.Err())
		}
	}

	b.circuitBreaker.OnFailure()
	return nil, fmt.Errorf("bedrock call failed after %d attempts: %v", b.retryConfig.MaxRetries+1, lastErr)
}

// calculateBackoffDelay calculates the delay for exponential backoff with optional jitter
func (b *bedrockService) calculateBackoffDelay(attempt int) time.Duration {
	// Calculate exponential backoff
	delay := float64(b.retryConfig.BaseDelay) * math.Pow(b.retryConfig.BackoffFactor, float64(attempt-1))

	// Apply maximum delay limit
	if delay > float64(b.retryConfig.MaxDelay) {
		delay = float64(b.retryConfig.MaxDelay)
	}

	// Add jitter to prevent thundering herd
	if b.retryConfig.JitterEnabled {
		jitter := delay * 0.1 * (2.0*math.Abs(float64(time.Now().UnixNano()%1000))/1000.0 - 1.0)
		delay += jitter
	}

	return time.Duration(delay)
}

// isRetryableError determines if an error is retryable
func (b *bedrockService) isRetryableError(err error) bool {
	if err == nil {
		return false
	}

	errStr := strings.ToLower(err.Error())

	// Retryable errors
	retryablePatterns := []string{
		"throttling",
		"rate limit",
		"timeout",
		"temporary",
		"service unavailable",
		"internal server error",
		"connection",
		"network",
		"502",
		"503",
		"504",
	}

	for _, pattern := range retryablePatterns {
		if strings.Contains(errStr, pattern) {
			return true
		}
	}

	// Non-retryable errors
	nonRetryablePatterns := []string{
		"access denied",
		"unauthorized",
		"forbidden",
		"invalid",
		"bad request",
		"400",
		"401",
		"403",
	}

	for _, pattern := range nonRetryablePatterns {
		if strings.Contains(errStr, pattern) {
			return false
		}
	}

	// Default to retryable for unknown errors
	return true
}

// invokeBedrock makes a single call to Bedrock
func (b *bedrockService) invokeBedrock(ctx context.Context, request GenerateUsecaseRequest) (*BedrockResponse, error) {
	startTime := time.Now()

	// Create the prompt for Bedrock
	prompt := b.createPrompt(request)
	log.Printf("Invoking Bedrock model %s with prompt length: %d", b.modelID, len(prompt))

	// Prepare the request body for Claude
	requestBody := map[string]interface{}{
		"anthropic_version": "bedrock-2023-05-31",
		"max_tokens":        4096,
		"temperature":       0.1,
		"top_p":             0.9,
		"messages": []map[string]interface{}{
			{
				"role":    "user",
				"content": prompt,
			},
		},
	}

	requestBodyBytes, err := json.Marshal(requestBody)
	if err != nil {
		log.Printf("Error marshaling request body: %v", err)
		return nil, fmt.Errorf("failed to marshal request: %v", err)
	}

	// Call Bedrock
	input := &bedrockruntime.InvokeModelInput{
		ModelId:     aws.String(b.modelID),
		ContentType: aws.String("application/json"),
		Accept:      aws.String("application/json"),
		Body:        requestBodyBytes,
	}

	result, err := b.client.InvokeModel(ctx, input)
	duration := time.Since(startTime)

	if err != nil {
		log.Printf("Bedrock model invocation failed after %v: %v", duration, err)
		return nil, fmt.Errorf("bedrock invocation failed: %v", err)
	}

	log.Printf("Bedrock model invocation completed in %v", duration)

	// Parse the response
	var response map[string]interface{}
	if err := json.Unmarshal(result.Body, &response); err != nil {
		log.Printf("Error unmarshaling Bedrock response: %v", err)
		return nil, fmt.Errorf("failed to parse bedrock response: %v", err)
	}

	// Extract the generated content
	content, ok := response["content"].([]interface{})
	if !ok || len(content) == 0 {
		log.Printf("Invalid response format from Bedrock: %+v", response)
		return nil, fmt.Errorf("invalid response format from bedrock")
	}

	firstContent, ok := content[0].(map[string]interface{})
	if !ok {
		log.Printf("Invalid content format from Bedrock: %+v", content[0])
		return nil, fmt.Errorf("invalid content format from bedrock")
	}

	generatedText, ok := firstContent["text"].(string)
	if !ok {
		log.Printf("Invalid text format from Bedrock: %+v", firstContent)
		return nil, fmt.Errorf("invalid text format from bedrock")
	}

	// Clean up the generated text to extract JSON
	generatedJSON := b.extractJSON(generatedText)

	log.Printf("Successfully generated JSON from Bedrock (length: %d chars, total time: %v)", len(generatedJSON), time.Since(startTime))

	return &BedrockResponse{
		GeneratedJSON: generatedJSON,
		Confidence:    0.9, // Default confidence
	}, nil
}

// createPrompt creates the prompt for Bedrock based on the user journey
func (b *bedrockService) createPrompt(request GenerateUsecaseRequest) string {
	currentTime := time.Now().UTC().Format(time.RFC3339)

	// Escape quotes in user input for JSON safety
	escapedTitle := strings.ReplaceAll(request.Title, `"`, `\"`)
	escapedJourney := strings.ReplaceAll(request.UserJourney, `"`, `\"`)

	prompt := `You are an expert test automation engineer. Convert the following user journey description into a structured JSON format for automated web testing.

User Journey Details:
- Title: (Wizzard)` + request.Title + `
- Starting URL: ` + request.StartingURL + `
- Journey Description: ` + request.UserJourney + `

Generate a JSON object that matches this EXACT schema. This JSON will be imported into a test automation system, so it must be perfectly formatted and valid:

{
  "exportVersion": "1.0",
  "exportedAt": "` + currentTime + `",
  "usecase": {
    "name": "(Wizzard) ` + escapedTitle + `",
    "description": "Generated from user journey: ` + escapedJourney + `",
    "starting_url": "` + request.StartingURL + `",
    "active": true,
    "headless": false,
    "region": "` + request.Region + `",
    "tags": []
  },
  "steps": [
    {
      "sort": 1,
      "instruction": "Navigate to the starting page",
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
}

CRITICAL REQUIREMENTS:
1. Generate comprehensive steps covering the entire user journey
2. Include navigation steps for page interactions (clicking, typing, etc.)
3. Include validation steps for expected outcomes and assertions, only values can be asserted. the types are string, bool and number.
4. Add validation steps for expected outcomes and assertions
5. Use ONLY these step types: "navigation", "validation", "secret"
6. Validation operators for string are exact, exact_case_insensitive, contains and contains_case_insensitive
7. Validation operators for bool are exact
8. Validation operators for number are equals, less_then, greater_then, greater_or_equal_then and less_or_equal_then
9. Validation step instruction must start with "return the value for ...". like: "return the number of products on the page".
10. Each step MUST have ALL fields present, use empty strings ("") for unused fields
11. Sort steps sequentially starting from 1 (no gaps or duplicates)
12. All strings must be properly escaped for JSON
13. Return ONLY the JSON object, no markdown, no explanations, no additional text
14. Ensure the JSON is valid and can be parsed
15. You do not need a step to move to the start page.
16. Secret steps must always focus an input field only.
17. Instructions must be written as instructions. Like "click the search button" or "Return the amount of items in the basket"

Step Type Guidelines:
- "navigation": For clicking buttons, filling forms, navigating pages
- "validation": For checking page content, verifying elements exist
- "secret": For using stored credentials (set secret_key field)

Generate the complete, valid JSON now:`

	return prompt
}

// extractJSON extracts JSON from the generated text with improved parsing
func (b *bedrockService) extractJSON(text string) string {
	// Remove common markdown artifacts
	text = strings.ReplaceAll(text, "```json", "")
	text = strings.ReplaceAll(text, "```", "")
	text = strings.TrimSpace(text)

	// Find the first opening brace
	start := strings.Index(text, "{")
	if start == -1 {
		log.Printf("No opening brace found in generated text")
		return text
	}

	// Find the matching closing brace by counting braces
	braceCount := 0
	end := -1
	for i := start; i < len(text); i++ {
		if text[i] == '{' {
			braceCount++
		} else if text[i] == '}' {
			braceCount--
			if braceCount == 0 {
				end = i
				break
			}
		}
	}

	if end == -1 {
		log.Printf("No matching closing brace found")
		// Fallback to last brace
		end = strings.LastIndex(text, "}")
		if end == -1 || end <= start {
			return text
		}
	}

	extracted := text[start : end+1]
	log.Printf("Extracted JSON from position %d to %d (length: %d)", start, end, len(extracted))
	return extracted
}

// ValidationErrors represents multiple validation errors
type ValidationErrors struct {
	Errors []ValidationError `json:"errors"`
}

func (ve *ValidationErrors) Error() string {
	if len(ve.Errors) == 0 {
		return "validation failed"
	}
	if len(ve.Errors) == 1 {
		return ve.Errors[0].Message
	}
	var messages []string
	for _, err := range ve.Errors {
		messages = append(messages, err.Message)
	}
	return strings.Join(messages, "; ")
}

// ValidationError represents a single validation error
type ValidationError struct {
	Field   string `json:"field"`
	Message string `json:"message"`
	Code    string `json:"code"`
}

func (e *ValidationError) Error() string {
	return e.Message
}

// validateRequest validates and sanitizes the incoming request using enhanced validation
func validateRequest(req *GenerateUsecaseRequest) error {
	var errors []ValidationError

	// Validate and sanitize title
	sanitizedTitle, titleErrors := user_journey.ValidateTitle(req.Title)
	if len(titleErrors) > 0 {
		for _, err := range titleErrors {
			errors = append(errors, ValidationError{
				Field:   "title",
				Message: err,
				Code:    getErrorCode(err),
			})
		}
	} else {
		req.Title = sanitizedTitle
	}

	// Validate and sanitize URL
	sanitizedURL, urlErrors := user_journey.ValidateURL(req.StartingURL)
	if len(urlErrors) > 0 {
		for _, err := range urlErrors {
			errors = append(errors, ValidationError{
				Field:   "startingUrl",
				Message: err,
				Code:    getErrorCode(err),
			})
		}
	} else {
		req.StartingURL = sanitizedURL
	}

	// Validate and sanitize user journey
	sanitizedJourney, journeyErrors := user_journey.ValidateUserJourney(req.UserJourney)
	if len(journeyErrors) > 0 {
		for _, err := range journeyErrors {
			errors = append(errors, ValidationError{
				Field:   "userJourney",
				Message: err,
				Code:    getErrorCode(err),
			})
		}
	} else {
		req.UserJourney = sanitizedJourney
	}

	// Validate region
	if strings.TrimSpace(req.Region) == "" {
		errors = append(errors, ValidationError{
			Field:   "region",
			Message: "Region is required",
			Code:    "REQUIRED",
		})
	} else {
		// Validate region format (basic validation)
		validRegions := []string{"us-east-1", "us-west-2", "ap-southeast-2", "eu-central-1"}
		isValidRegion := false
		for _, validRegion := range validRegions {
			if req.Region == validRegion {
				isValidRegion = true
				break
			}
		}
		if !isValidRegion {
			errors = append(errors, ValidationError{
				Field:   "region",
				Message: "Invalid region. Must be one of: us-east-1, us-west-2, ap-southeast-2, eu-central-1",
				Code:    "INVALID_FORMAT",
			})
		}
	}

	if len(errors) > 0 {
		return &ValidationErrors{Errors: errors}
	}

	return nil
}

// getErrorCode maps error messages to error codes
func getErrorCode(errorMessage string) string {
	lowerMsg := strings.ToLower(errorMessage)

	if strings.Contains(lowerMsg, "required") {
		return "REQUIRED_FIELD"
	}
	if strings.Contains(lowerMsg, "characters or less") || strings.Contains(lowerMsg, "exceeded") {
		return "MAX_LENGTH_EXCEEDED"
	}
	if strings.Contains(lowerMsg, "at least") || strings.Contains(lowerMsg, "minimum") {
		return "MIN_LENGTH_NOT_MET"
	}
	if strings.Contains(lowerMsg, "invalid") || strings.Contains(lowerMsg, "format") {
		return "INVALID_FORMAT"
	}
	if strings.Contains(lowerMsg, "url") {
		return "INVALID_URL"
	}
	if strings.Contains(lowerMsg, "security") || strings.Contains(lowerMsg, "threat") || strings.Contains(lowerMsg, "dangerous") {
		return "SECURITY_VIOLATION"
	}

	return "VALIDATION_ERROR"
}

// sanitizeInput removes potentially harmful characters and normalizes whitespace
func sanitizeInput(input string) string {
	// Remove null bytes and control characters except newlines and tabs
	var result strings.Builder
	for _, r := range input {
		if r == '\n' || r == '\t' || r == '\r' || (r >= 32 && r != 127) {
			result.WriteRune(r)
		}
	}

	// Normalize whitespace
	normalized := strings.TrimSpace(result.String())
	// Replace multiple consecutive whitespace with single space
	normalized = strings.Join(strings.Fields(normalized), " ")

	return normalized
}

// sanitizeURL sanitizes and validates URL format
func sanitizeURL(url string) string {
	url = strings.TrimSpace(url)
	// Remove any potential XSS attempts
	url = strings.ReplaceAll(url, "javascript:", "")
	url = strings.ReplaceAll(url, "data:", "")
	url = strings.ReplaceAll(url, "vbscript:", "")
	return url
}

// isValidTitle checks if title contains only allowed characters
func isValidTitle(title string) bool {
	// Allow letters, numbers, spaces, hyphens, underscores, and common punctuation
	for _, r := range title {
		if !((r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') ||
			(r >= '0' && r <= '9') || r == ' ' || r == '-' ||
			r == '_' || r == '.' || r == ',' || r == ':' ||
			r == '(' || r == ')' || r == '[' || r == ']') {
			return false
		}
	}
	return true
}

// isValidURL validates URL format more thoroughly
func isValidURL(url string) bool {
	if !strings.HasPrefix(url, "http://") && !strings.HasPrefix(url, "https://") {
		return false
	}

	// Basic URL structure validation
	if strings.Contains(url, " ") {
		return false
	}

	// Check for minimum valid URL structure
	if len(url) < 10 { // Minimum: https://a.b
		return false
	}

	// Ensure there's a domain after the protocol
	protocolEnd := strings.Index(url, "://")
	if protocolEnd == -1 || len(url) <= protocolEnd+3 {
		return false
	}

	domain := url[protocolEnd+3:]
	if strings.HasPrefix(domain, "/") || strings.HasPrefix(domain, "?") {
		return false
	}

	return true
}

// containsSuspiciousContent checks for potentially harmful content
func containsSuspiciousContent(content string) bool {
	suspiciousPatterns := []string{
		"<script",
		"javascript:",
		"data:",
		"vbscript:",
		"onload=",
		"onerror=",
		"onclick=",
		"eval(",
		"document.cookie",
		"window.location",
		"alert(",
		"confirm(",
		"prompt(",
	}

	lowerContent := strings.ToLower(content)
	for _, pattern := range suspiciousPatterns {
		if strings.Contains(lowerContent, pattern) {
			return true
		}
	}

	return false
}

// LogContext holds contextual information for logging
type LogContext struct {
	RequestID string
	UserID    string
	UserEmail string
	Operation string
}

// logWithContext logs a message with contextual information
func logWithContext(ctx *LogContext, level string, message string, args ...interface{}) {
	prefix := fmt.Sprintf("[%s] [%s] [User: %s (%s)] [Op: %s]",
		level, ctx.RequestID, ctx.UserEmail, ctx.UserID, ctx.Operation)

	if len(args) > 0 {
		log.Printf(prefix+" "+message, args...)
	} else {
		log.Printf(prefix + " " + message)
	}
}

// handler is the main Lambda handler function
func handler(ctx context.Context, request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	requestID := request.RequestContext.RequestID
	if requestID == "" {
		requestID = fmt.Sprintf("req-%d", time.Now().UnixNano())
	}

	logCtx := &LogContext{
		RequestID: requestID,
		Operation: "generate_usecase",
	}

	logWithContext(logCtx, "INFO", "Received request (body length: %d)", len(request.Body))

	// Parse the request body
	var req GenerateUsecaseRequest
	if err := json.Unmarshal([]byte(request.Body), &req); err != nil {
		logWithContext(logCtx, "ERROR", "Failed to unmarshal request: %v", err)
		return createErrorResponseWithCode(400, "Invalid request format",
			"Request body must be valid JSON", "INVALID_JSON"), nil
	}

	// Validate the request
	if err := validateRequest(&req); err != nil {
		logWithContext(logCtx, "WARN", "Request validation failed: %v", err)

		// Check if it's a ValidationErrors type for structured response
		if validationErrors, ok := err.(*ValidationErrors); ok {
			return createValidationErrorResponse(validationErrors), nil
		}

		return createErrorResponse(400, "Validation failed", err.Error()), nil
	}

	// Extract user information from Cognito claims
	claims, err := utils.DecodeClaims(request)
	if err != nil {
		logWithContext(logCtx, "ERROR", "Failed to decode claims: %v", err)
		return createErrorResponseWithCode(401, "Authentication failed",
			"Invalid or expired authentication token", "AUTH_FAILED"), nil
	}

	// Update log context with user information
	logCtx.UserID = claims.Sub
	logCtx.UserEmail = claims.Email
	logWithContext(logCtx, "INFO", "Processing generate usecase request")

	// Load AWS configuration
	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		logWithContext(logCtx, "ERROR", "Failed to load AWS config: %v", err)
		return createErrorResponseWithCode(500, "Internal server error",
			"Failed to initialize AWS services", "AWS_CONFIG_ERROR"), nil
	}

	// Create Bedrock service
	bedrockSvc := NewBedrockService(cfg)

	// Generate the usecase using Bedrock
	logWithContext(logCtx, "INFO", "Calling Bedrock service to generate usecase")
	bedrockResponse, err := bedrockSvc.GenerateUsecase(ctx, req)
	if err != nil {
		logWithContext(logCtx, "ERROR", "Bedrock service call failed: %v", err)

		// Categorize Bedrock errors
		errorCode := "BEDROCK_ERROR"
		errorMessage := "Failed to generate test case"

		if strings.Contains(err.Error(), "throttling") || strings.Contains(err.Error(), "rate limit") {
			errorCode = "RATE_LIMIT_EXCEEDED"
			errorMessage = "AI service is currently busy. Please try again in a moment"
		} else if strings.Contains(err.Error(), "timeout") {
			errorCode = "TIMEOUT_ERROR"
			errorMessage = "AI service request timed out. Please try again"
		} else if strings.Contains(err.Error(), "access denied") || strings.Contains(err.Error(), "unauthorized") {
			errorCode = "ACCESS_DENIED"
			errorMessage = "AI service access denied"
		}

		return createErrorResponseWithCode(502, errorMessage, err.Error(), errorCode), nil
	}

	// Sanitize and validate the generated JSON
	logWithContext(logCtx, "INFO", "Sanitizing and validating generated JSON")
	sanitizedJSON := user_journey.SanitizeAndFixJSON(bedrockResponse.GeneratedJSON)
	validationResult := user_journey.ValidateAndParseJSON(sanitizedJSON)

	if !validationResult.IsValid {
		logWithContext(logCtx, "ERROR", "Generated JSON validation failed: %v", validationResult.Errors)
		return createErrorResponseWithCode(502, "AI service error",
			fmt.Sprintf("Generated test case validation failed: %s", strings.Join(validationResult.Errors, "; ")),
			"INVALID_GENERATED_JSON"), nil
	}

	logWithContext(logCtx, "INFO", "JSON validation successful, %d steps generated", len(validationResult.Schema.Steps))

	// Create successful response with sanitized JSON
	response := GenerateUsecaseResponse{
		Success:     true,
		UsecaseData: sanitizedJSON,
		Message:     "Test case generated successfully",
	}

	responseBody, err := json.Marshal(response)
	if err != nil {
		logWithContext(logCtx, "ERROR", "Failed to marshal response: %v", err)
		return createErrorResponseWithCode(500, "Internal server error",
			"Failed to create response", "RESPONSE_MARSHAL_ERROR"), nil
	}

	logWithContext(logCtx, "INFO", "Successfully generated usecase, returning response")
	return events.APIGatewayProxyResponse{
		StatusCode: 200,
		Headers:    getCORSHeaders(),
		Body:       string(responseBody),
	}, nil
}

// ErrorResponse represents a structured error response
type ErrorResponse struct {
	Success bool                   `json:"success"`
	Message string                 `json:"message"`
	Error   string                 `json:"error,omitempty"`
	Code    string                 `json:"code,omitempty"`
	Details map[string]interface{} `json:"details,omitempty"`
}

// createErrorResponse creates a standardized error response
func createErrorResponse(statusCode int, message, details string) events.APIGatewayProxyResponse {
	return createErrorResponseWithCode(statusCode, message, details, "")
}

// createErrorResponseWithCode creates a standardized error response with error code
func createErrorResponseWithCode(statusCode int, message, details, code string) events.APIGatewayProxyResponse {
	errorResponse := ErrorResponse{
		Success: false,
		Message: message,
		Error:   details,
		Code:    code,
	}

	body, _ := json.Marshal(errorResponse)

	return events.APIGatewayProxyResponse{
		StatusCode: statusCode,
		Headers:    getCORSHeaders(),
		Body:       string(body),
	}
}

// createValidationErrorResponse creates a structured validation error response
func createValidationErrorResponse(validationErrors *ValidationErrors) events.APIGatewayProxyResponse {
	errorResponse := ErrorResponse{
		Success: false,
		Message: "Request validation failed",
		Error:   validationErrors.Error(),
		Code:    "VALIDATION_ERROR",
		Details: map[string]interface{}{
			"validationErrors": validationErrors.Errors,
		},
	}

	body, _ := json.Marshal(errorResponse)

	return events.APIGatewayProxyResponse{
		StatusCode: 400,
		Headers:    getCORSHeaders(),
		Body:       string(body),
	}
}

// getCORSHeaders returns standard CORS headers
func getCORSHeaders() map[string]string {
	return map[string]string{
		"Content-Type":                 "application/json",
		"Access-Control-Allow-Origin":  "*",
		"Access-Control-Allow-Methods": "POST, OPTIONS",
		"Access-Control-Allow-Headers": "Content-Type, Authorization",
	}
}

func main() {
	lambda.Start(handler)
}
