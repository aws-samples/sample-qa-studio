package user_journey

import (
	"encoding/json"
	"fmt"
	"net/url"
	"regexp"
	"strings"
	"unicode"
)

// ImportSchema represents the expected structure for import_usecase
type ImportSchema struct {
	ExportVersion string           `json:"exportVersion"`
	ExportedAt    string           `json:"exportedAt"`
	Usecase       UsecaseSchema    `json:"usecase"`
	Steps         []StepSchema     `json:"steps"`
	Variables     []VariableSchema `json:"variables"`
	Secrets       []SecretSchema   `json:"secrets"`
	Hooks         *HooksSchema     `json:"hooks,omitempty"`
}

type UsecaseSchema struct {
	Name        string   `json:"name"`
	Description string   `json:"description"`
	StartingURL string   `json:"starting_url"`
	Active      bool     `json:"active"`
	Tags        []string `json:"tags"`
}

type StepSchema struct {
	Sort               int    `json:"sort"`
	Instruction        string `json:"instruction"`
	StepType           string `json:"step_type"`
	SecretKey          string `json:"secret_key,omitempty"`
	CaptureVariable    string `json:"capture_variable,omitempty"`
	ValidationType     string `json:"validation_type,omitempty"`
	ValidationOperator string `json:"validation_operator,omitempty"`
	ValidationValue    string `json:"validation_value,omitempty"`
	AssertionVariable  string `json:"assertion_variable,omitempty"`
	ValueStep          string `json:"value_step,omitempty"`
	ValueType          string `json:"value_type,omitempty"`
}

type VariableSchema struct {
	Key   string `json:"key"`
	Value string `json:"value"`
}

type SecretSchema struct {
	Key         string  `json:"key"`
	Description string  `json:"description"`
	Value       *string `json:"value"`
	Placeholder string  `json:"placeholder"`
}

type HooksSchema struct {
	BeforeScript string `json:"beforeScript"`
	AfterScript  string `json:"afterScript"`
}

// ValidationResult represents the result of JSON validation
type ValidationResult struct {
	IsValid bool          `json:"isValid"`
	Errors  []string      `json:"errors"`
	Schema  *ImportSchema `json:"schema,omitempty"`
}

// ValidateAndParseJSON validates the generated JSON against the import_usecase schema
func ValidateAndParseJSON(jsonStr string) *ValidationResult {
	result := &ValidationResult{
		IsValid: false,
		Errors:  []string{},
	}

	// First, check if it's valid JSON
	var rawData interface{}
	if err := json.Unmarshal([]byte(jsonStr), &rawData); err != nil {
		result.Errors = append(result.Errors, fmt.Sprintf("Invalid JSON format: %v", err))
		return result
	}

	// Try to parse into our schema
	var schema ImportSchema
	if err := json.Unmarshal([]byte(jsonStr), &schema); err != nil {
		result.Errors = append(result.Errors, fmt.Sprintf("JSON does not match expected schema: %v", err))
		return result
	}

	// Validate required fields and structure
	errors := validateImportSchema(&schema)
	if len(errors) > 0 {
		result.Errors = errors
		return result
	}

	result.IsValid = true
	result.Schema = &schema
	return result
}

// validateImportSchema performs detailed validation of the import schema
func validateImportSchema(schema *ImportSchema) []string {
	var errors []string

	// Validate export version
	if schema.ExportVersion == "" {
		errors = append(errors, "exportVersion is required")
	} else if schema.ExportVersion != "1.0" {
		errors = append(errors, "exportVersion must be '1.0'")
	}

	// Validate exportedAt
	if schema.ExportedAt == "" {
		errors = append(errors, "exportedAt is required")
	}

	// Validate usecase
	usecaseErrors := validateUsecaseSchema(&schema.Usecase)
	errors = append(errors, usecaseErrors...)

	// Validate steps
	if len(schema.Steps) == 0 {
		errors = append(errors, "at least one step is required")
	} else {
		stepErrors := validateStepsSchema(schema.Steps)
		errors = append(errors, stepErrors...)
	}

	// Validate variables (optional but if present, must be valid)
	if schema.Variables != nil {
		variableErrors := validateVariablesSchema(schema.Variables)
		errors = append(errors, variableErrors...)
	}

	// Validate secrets (optional but if present, must be valid)
	if schema.Secrets != nil {
		secretErrors := validateSecretsSchema(schema.Secrets)
		errors = append(errors, secretErrors...)
	}

	return errors
}

// validateUsecaseSchema validates the usecase object
func validateUsecaseSchema(usecase *UsecaseSchema) []string {
	var errors []string

	if strings.TrimSpace(usecase.Name) == "" {
		errors = append(errors, "usecase.name is required")
	}

	if strings.TrimSpace(usecase.Description) == "" {
		errors = append(errors, "usecase.description is required")
	}

	if strings.TrimSpace(usecase.StartingURL) == "" {
		errors = append(errors, "usecase.starting_url is required")
	} else if !strings.HasPrefix(usecase.StartingURL, "http://") && !strings.HasPrefix(usecase.StartingURL, "https://") {
		errors = append(errors, "usecase.starting_url must be a valid HTTP/HTTPS URL")
	}

	if usecase.Tags == nil {
		errors = append(errors, "usecase.tags must be an array (can be empty)")
	}

	return errors
}

// validateStepsSchema validates the steps array
func validateStepsSchema(steps []StepSchema) []string {
	var errors []string
	validStepTypes := map[string]bool{
		"navigation":     true,
		"validation":     true,
		"secret":         true,
		"retrieve_value": true,
		"assertion":      true,
	}
	validOperators := map[string]bool{
		"exact":                     true,
		"exact_case_insensitive":    true,
		"contains":                  true,
		"contains_case_insensitive": true,
		"equals":                    true,
		"not_equals":                true,
		"greater_then":              true,
		"less_then":                 true,
		"greater_or_equal_then":     true,
		"less_or_equal_then":        true,
	}

	sortNumbers := make(map[int]bool)

	for i, step := range steps {
		stepPrefix := fmt.Sprintf("steps[%d]", i)

		// Validate sort number
		if step.Sort <= 0 {
			errors = append(errors, fmt.Sprintf("%s.sort must be a positive integer", stepPrefix))
		}
		if sortNumbers[step.Sort] {
			errors = append(errors, fmt.Sprintf("%s.sort %d is duplicated", stepPrefix, step.Sort))
		}
		sortNumbers[step.Sort] = true

		// Validate instruction
		if strings.TrimSpace(step.Instruction) == "" {
			errors = append(errors, fmt.Sprintf("%s.instruction is required", stepPrefix))
		}

		// Validate step_type
		if !validStepTypes[step.StepType] {
			errors = append(errors, fmt.Sprintf("%s.step_type must be one of: navigation, validation, secret, retrieve_value", stepPrefix))
		}

		// Validate validation-specific fields
		if step.StepType == "validation" {
			if step.ValidationType == "" {
				errors = append(errors, fmt.Sprintf("%s.validation_type is required for validation steps", stepPrefix))
			}
			if step.ValidationOperator != "" && !validOperators[step.ValidationOperator] {
				errors = append(errors, fmt.Sprintf("%s.validation_operator must be one of: exact, exact_case_insensitive, contains, contains_case_insensitive, equals, greater_then, less_then, greater_or_equal_then, less_or_equal_then", stepPrefix))
			}
		}

		// Validate secret-specific fields
		if step.StepType == "secret" && strings.TrimSpace(step.SecretKey) == "" {
			errors = append(errors, fmt.Sprintf("%s.secret_key is required for secret steps", stepPrefix))
		}

		// Validate retrieve_value-specific fields
		if step.StepType == "retrieve_value" {
			if strings.TrimSpace(step.CaptureVariable) == "" {
				errors = append(errors, fmt.Sprintf("%s.capture_variable is required for retrieve_value steps", stepPrefix))
			}
			if strings.TrimSpace(step.ValueType) == "" {
				errors = append(errors, fmt.Sprintf("%s.value_type is required for retrieve_value steps", stepPrefix))
			}
		}
	}

	return errors
}

// validateVariablesSchema validates the variables array
func validateVariablesSchema(variables []VariableSchema) []string {
	var errors []string
	keys := make(map[string]bool)

	for i, variable := range variables {
		varPrefix := fmt.Sprintf("variables[%d]", i)

		if strings.TrimSpace(variable.Key) == "" {
			errors = append(errors, fmt.Sprintf("%s.key is required", varPrefix))
		} else if keys[variable.Key] {
			errors = append(errors, fmt.Sprintf("%s.key '%s' is duplicated", varPrefix, variable.Key))
		}
		keys[variable.Key] = true

		if strings.TrimSpace(variable.Value) == "" {
			errors = append(errors, fmt.Sprintf("%s.value is required", varPrefix))
		}
	}

	return errors
}

// validateSecretsSchema validates the secrets array
func validateSecretsSchema(secrets []SecretSchema) []string {
	var errors []string
	keys := make(map[string]bool)

	for i, secret := range secrets {
		secretPrefix := fmt.Sprintf("secrets[%d]", i)

		if strings.TrimSpace(secret.Key) == "" {
			errors = append(errors, fmt.Sprintf("%s.key is required", secretPrefix))
		} else if keys[secret.Key] {
			errors = append(errors, fmt.Sprintf("%s.key '%s' is duplicated", secretPrefix, secret.Key))
		}
		keys[secret.Key] = true

		if strings.TrimSpace(secret.Description) == "" {
			errors = append(errors, fmt.Sprintf("%s.description is required", secretPrefix))
		}
	}

	return errors
}

// Security patterns for input validation
var (
	// XSS detection patterns
	xssPattern = regexp.MustCompile(`(?i)<script|javascript:|on\w+\s*=|<iframe|<object|<embed`)

	// Path traversal detection patterns
	pathTraversalPattern = regexp.MustCompile(`\.\.[\/\\]|%2e%2e[\/\\]|\.\.%2f|\.\.%5c`)

	// Valid title pattern (alphanumeric, spaces, hyphens, underscores)
	titlePattern = regexp.MustCompile(`^[a-zA-Z0-9\s\-_]+$`)
)

// SecurityValidationResult represents the result of security validation
type SecurityValidationResult struct {
	IsSecure bool     `json:"isSecure"`
	Threats  []string `json:"threats"`
}

// ValidateInputSecurity checks input for security threats
func ValidateInputSecurity(input string) *SecurityValidationResult {
	result := &SecurityValidationResult{
		IsSecure: true,
		Threats:  []string{},
	}

	if xssPattern.MatchString(input) {
		result.IsSecure = false
		result.Threats = append(result.Threats, "Potential XSS content detected")
	}

	if pathTraversalPattern.MatchString(input) {
		result.IsSecure = false
		result.Threats = append(result.Threats, "Potential path traversal content detected")
	}

	return result
}

// SanitizeInput removes potentially dangerous characters and normalizes input
func SanitizeInput(input string) string {
	// Remove control characters except newlines and tabs
	sanitized := strings.Map(func(r rune) rune {
		if unicode.IsControl(r) && r != '\n' && r != '\t' && r != '\r' {
			return -1
		}
		return r
	}, input)

	// Normalize whitespace
	sanitized = regexp.MustCompile(`\s+`).ReplaceAllString(sanitized, " ")

	// Trim whitespace
	sanitized = strings.TrimSpace(sanitized)

	return sanitized
}

// ValidateTitle validates and sanitizes a title input
func ValidateTitle(title string) (string, []string) {
	var errors []string

	// Sanitize input
	sanitized := SanitizeInput(title)

	// Security check
	securityResult := ValidateInputSecurity(sanitized)
	if !securityResult.IsSecure {
		errors = append(errors, securityResult.Threats...)
		return "", errors
	}

	// Length validation
	if len(sanitized) == 0 {
		errors = append(errors, "Title is required")
		return "", errors
	}

	if len(sanitized) > 200 {
		errors = append(errors, "Title must be 200 characters or less")
		return "", errors
	}

	if len(sanitized) < 3 {
		errors = append(errors, "Title must be at least 3 characters long")
		return "", errors
	}

	// Pattern validation
	if !titlePattern.MatchString(sanitized) {
		errors = append(errors, "Title can only contain letters, numbers, spaces, hyphens, and underscores")
		return "", errors
	}

	// Check for meaningful content
	words := strings.Fields(sanitized)
	if len(words) == 0 {
		errors = append(errors, "Title must contain meaningful content")
		return "", errors
	}

	return sanitized, errors
}

// ValidateURL validates and sanitizes a URL input
func ValidateURL(urlStr string) (string, []string) {
	var errors []string

	// Sanitize input
	sanitized := SanitizeInput(urlStr)

	// Security check
	securityResult := ValidateInputSecurity(sanitized)
	if !securityResult.IsSecure {
		errors = append(errors, securityResult.Threats...)
		return "", errors
	}

	// Required validation
	if len(sanitized) == 0 {
		errors = append(errors, "Starting URL is required")
		return "", errors
	}

	// URL format validation
	parsedURL, err := url.Parse(sanitized)
	if err != nil {
		errors = append(errors, "Invalid URL format")
		return "", errors
	}

	// Scheme validation
	if parsedURL.Scheme != "http" && parsedURL.Scheme != "https" {
		errors = append(errors, "URL must start with http:// or https://")
		return "", errors
	}

	// Host validation
	if parsedURL.Host == "" {
		errors = append(errors, "URL must include a valid host")
		return "", errors
	}

	// Check for suspicious hosts
	if strings.Contains(parsedURL.Host, "..") || len(parsedURL.Host) < 3 {
		errors = append(errors, "URL host appears to be invalid")
		return "", errors
	}

	return sanitized, errors
}

// ValidateUserJourney validates and sanitizes a user journey description
func ValidateUserJourney(journey string) (string, []string) {
	var errors []string

	// Sanitize input
	sanitized := SanitizeInput(journey)

	// Security check
	securityResult := ValidateInputSecurity(sanitized)
	if !securityResult.IsSecure {
		errors = append(errors, securityResult.Threats...)
		return "", errors
	}

	// Required validation
	if len(sanitized) == 0 {
		errors = append(errors, "User journey description is required")
		return "", errors
	}

	// Length validation
	if len(sanitized) < 50 {
		errors = append(errors, "User journey description must be at least 50 characters")
		return "", errors
	}

	if len(sanitized) > 2000 {
		errors = append(errors, "User journey description must be 2000 characters or less")
		return "", errors
	}

	// Content validation
	words := strings.Fields(sanitized)
	if len(words) < 10 {
		errors = append(errors, "User journey description should contain more detailed steps")
		return "", errors
	}

	// Check for action words
	actionWords := []string{"click", "enter", "navigate", "select", "submit", "verify", "check", "fill", "choose", "confirm", "type", "press", "scroll", "hover"}
	hasActions := false
	lowerJourney := strings.ToLower(sanitized)

	for _, action := range actionWords {
		if strings.Contains(lowerJourney, action) {
			hasActions = true
			break
		}
	}

	if !hasActions {
		errors = append(errors, "User journey should include specific actions (click, enter, navigate, etc.)")
		return "", errors
	}

	return sanitized, errors
}

// SanitizeAndFixJSON attempts to fix common issues in generated JSON
func SanitizeAndFixJSON(jsonStr string) string {
	// Remove any markdown code block markers
	jsonStr = strings.ReplaceAll(jsonStr, "```json", "")
	jsonStr = strings.ReplaceAll(jsonStr, "```", "")

	// Trim whitespace
	jsonStr = strings.TrimSpace(jsonStr)

	// Ensure it starts and ends with braces
	if !strings.HasPrefix(jsonStr, "{") {
		start := strings.Index(jsonStr, "{")
		if start != -1 {
			jsonStr = jsonStr[start:]
		}
	}

	if !strings.HasSuffix(jsonStr, "}") {
		end := strings.LastIndex(jsonStr, "}")
		if end != -1 {
			jsonStr = jsonStr[:end+1]
		}
	}

	return jsonStr
}
