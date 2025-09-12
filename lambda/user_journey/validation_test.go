package user_journey

import (
	"strings"
	"testing"
)

func TestValidateTitle(t *testing.T) {
	tests := []struct {
		name        string
		input       string
		expectValid bool
		expectError string
	}{
		{
			name:        "valid title",
			input:       "Valid Test Title",
			expectValid: true,
		},
		{
			name:        "empty title",
			input:       "",
			expectValid: false,
			expectError: "required",
		},
		{
			name:        "too long title",
			input:       strings.Repeat("a", 201),
			expectValid: false,
			expectError: "200 characters",
		},
		{
			name:        "too short title",
			input:       "ab",
			expectValid: false,
			expectError: "3 characters",
		},
		{
			name:        "invalid characters",
			input:       "Title with @#$%",
			expectValid: false,
			expectError: "letters, numbers",
		},
		{
			name:        "valid with hyphens and underscores",
			input:       "Valid-Test_Title 123",
			expectValid: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			sanitized, errors := ValidateTitle(tt.input)

			if tt.expectValid {
				if len(errors) > 0 {
					t.Errorf("Expected valid title, got errors: %v", errors)
				}
				if sanitized == "" {
					t.Errorf("Expected sanitized title, got empty string")
				}
			} else {
				if len(errors) == 0 {
					t.Errorf("Expected validation errors, got none")
				}
				if tt.expectError != "" {
					found := false
					for _, err := range errors {
						if strings.Contains(strings.ToLower(err), strings.ToLower(tt.expectError)) {
							found = true
							break
						}
					}
					if !found {
						t.Errorf("Expected error containing '%s', got: %v", tt.expectError, errors)
					}
				}
			}
		})
	}
}

func TestValidateURL(t *testing.T) {
	tests := []struct {
		name        string
		input       string
		expectValid bool
		expectError string
	}{
		{
			name:        "valid https URL",
			input:       "https://example.com",
			expectValid: true,
		},
		{
			name:        "valid http URL",
			input:       "http://localhost:3000",
			expectValid: true,
		},
		{
			name:        "empty URL",
			input:       "",
			expectValid: false,
			expectError: "required",
		},
		{
			name:        "no protocol",
			input:       "example.com",
			expectValid: false,
			expectError: "http://",
		},
		{
			name:        "invalid protocol",
			input:       "ftp://example.com",
			expectValid: false,
			expectError: "http://",
		},
		{
			name:        "malformed URL",
			input:       "https://",
			expectValid: false,
			expectError: "valid host",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			sanitized, errors := ValidateURL(tt.input)

			if tt.expectValid {
				if len(errors) > 0 {
					t.Errorf("Expected valid URL, got errors: %v", errors)
				}
				if sanitized == "" {
					t.Errorf("Expected sanitized URL, got empty string")
				}
			} else {
				if len(errors) == 0 {
					t.Errorf("Expected validation errors, got none")
				}
				if tt.expectError != "" {
					found := false
					for _, err := range errors {
						if strings.Contains(strings.ToLower(err), strings.ToLower(tt.expectError)) {
							found = true
							break
						}
					}
					if !found {
						t.Errorf("Expected error containing '%s', got: %v", tt.expectError, errors)
					}
				}
			}
		})
	}
}

func TestValidateUserJourney(t *testing.T) {
	tests := []struct {
		name        string
		input       string
		expectValid bool
		expectError string
	}{
		{
			name:        "valid journey with actions",
			input:       "User navigates to login page, enters email and password, clicks login button, and should be redirected to dashboard",
			expectValid: true,
		},
		{
			name:        "empty journey",
			input:       "",
			expectValid: false,
			expectError: "required",
		},
		{
			name:        "too short journey",
			input:       "User clicks button",
			expectValid: false,
			expectError: "50 characters",
		},
		{
			name:        "too long journey",
			input:       strings.Repeat("a", 2001),
			expectValid: false,
			expectError: "2000 characters",
		},
		{
			name:        "no action words",
			input:       "This is a very long description that does not contain any action words and should fail validation because it lacks specific user interactions and meaningful steps",
			expectValid: false,
			expectError: "actions",
		},
		{
			name:        "too few words",
			input:       "User does something with the application interface today",
			expectValid: false,
			expectError: "detailed steps",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			sanitized, errors := ValidateUserJourney(tt.input)

			if tt.expectValid {
				if len(errors) > 0 {
					t.Errorf("Expected valid journey, got errors: %v", errors)
				}
				if sanitized == "" {
					t.Errorf("Expected sanitized journey, got empty string")
				}
			} else {
				if len(errors) == 0 {
					t.Errorf("Expected validation errors, got none")
				}
				if tt.expectError != "" {
					found := false
					for _, err := range errors {
						if strings.Contains(strings.ToLower(err), strings.ToLower(tt.expectError)) {
							found = true
							break
						}
					}
					if !found {
						t.Errorf("Expected error containing '%s', got: %v", tt.expectError, errors)
					}
				}
			}
		})
	}
}

func TestValidateInputSecurity(t *testing.T) {
	tests := []struct {
		name         string
		input        string
		expectSecure bool
		expectThreat string
	}{
		{
			name:         "safe content",
			input:        "This is normal safe content",
			expectSecure: true,
		},
		{
			name:         "XSS attempt",
			input:        "<script>alert('xss')</script>",
			expectSecure: false,
			expectThreat: "XSS",
		},
		{
			name:         "SQL injection attempt",
			input:        "'; DROP TABLE users; --",
			expectSecure: false,
			expectThreat: "SQL injection",
		},
		{
			name:         "path traversal attempt",
			input:        "../../../etc/passwd",
			expectSecure: false,
			expectThreat: "path traversal",
		},
		{
			name:         "command injection attempt",
			input:        "test; rm -rf /",
			expectSecure: false,
			expectThreat: "command injection",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := ValidateInputSecurity(tt.input)

			if tt.expectSecure {
				if !result.IsSecure {
					t.Errorf("Expected secure input, got threats: %v", result.Threats)
				}
			} else {
				if result.IsSecure {
					t.Errorf("Expected security threats, got none")
				}
				if tt.expectThreat != "" {
					found := false
					for _, threat := range result.Threats {
						if strings.Contains(strings.ToLower(threat), strings.ToLower(tt.expectThreat)) {
							found = true
							break
						}
					}
					if !found {
						t.Errorf("Expected threat containing '%s', got: %v", tt.expectThreat, result.Threats)
					}
				}
			}
		})
	}
}

func TestSanitizeInput(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{
			name:     "normal text",
			input:    "Normal text content",
			expected: "Normal text content",
		},
		{
			name:     "text with control characters",
			input:    "Text\x00with\x01control\x02chars",
			expected: "Text with control chars",
		},
		{
			name:     "text with extra whitespace",
			input:    "  Multiple   spaces\t\tand\n\ntabs  ",
			expected: "Multiple spaces and tabs",
		},
		{
			name:     "empty input",
			input:    "",
			expected: "",
		},
		{
			name:     "only whitespace",
			input:    "   \t\n   ",
			expected: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := SanitizeInput(tt.input)
			if result != tt.expected {
				t.Errorf("Expected '%s', got '%s'", tt.expected, result)
			}
		})
	}
}
