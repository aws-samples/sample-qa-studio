import { errorManager } from './errorManager';

export interface ValidationRule {
  required?: boolean;
  minLength?: number;
  maxLength?: number;
  pattern?: RegExp;
  custom?: (value: string) => string | null;
}

export interface ValidationResult {
  isValid: boolean;
  error?: string;
  warning?: string;
  suggestion?: string;
}

export interface FieldValidationConfig {
  rules: ValidationRule;
  label: string;
  description?: string;
  examples?: string[];
  hints?: string[];
}

// Security patterns for input sanitization
const SECURITY_PATTERNS = {
  // Detect potential XSS attempts
  xss: /<script|javascript:|on\w+\s*=|<iframe|<object|<embed/i,
  // Detect path traversal attempts
  pathTraversal: /\.\.[\/\\]|%2e%2e[\/\\]|\.\.%2f|\.\.%5c/i,
};

export class ValidationManager {
  private static instance: ValidationManager;

  static getInstance(): ValidationManager {
    if (!ValidationManager.instance) {
      ValidationManager.instance = new ValidationManager();
    }
    return ValidationManager.instance;
  }

  // Sanitize input to prevent security issues (light sanitization for real-time input)
  sanitizeInput(value: string): string {
    if (!value) return value;

    // Only remove the most dangerous XSS characters during typing
    let sanitized = value
      .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
      .replace(/javascript:/gi, '')
      .replace(/on\w+\s*=/gi, '');

    return sanitized;
  }

  // Full sanitization for final validation and submission
  sanitizeForValidation(value: string): string {
    if (!value) return value;

    // Remove potential XSS characters
    let sanitized = value
      .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
      .replace(/javascript:/gi, '')
      .replace(/on\w+\s*=/gi, '');

    // Normalize whitespace only for validation
    sanitized = sanitized.replace(/\s+/g, ' ').trim();

    return sanitized;
  }

  // Check for security threats in input
  checkSecurity(value: string): ValidationResult {
    if (!value) return { isValid: true };

    for (const [type, pattern] of Object.entries(SECURITY_PATTERNS)) {
      if (pattern.test(value)) {
        return {
          isValid: false,
          error: `Input contains potentially unsafe content (${type}). Please remove special characters and try again.`
        };
      }
    }

    return { isValid: true };
  }

  // Validate individual field
  validateField(value: string, config: FieldValidationConfig): ValidationResult {
    const { rules, label } = config;

    // Security check first
    const securityResult = this.checkSecurity(value);
    if (!securityResult.isValid) {
      return securityResult;
    }

    // Sanitize input for validation
    const sanitizedValue = this.sanitizeForValidation(value);

    // Required validation
    if (rules.required && !sanitizedValue.trim()) {
      return {
        isValid: false,
        error: `${label} is required`,
        suggestion: config.examples?.[0] ? `Example: ${config.examples[0]}` : undefined
      };
    }

    // Skip other validations if field is empty and not required
    if (!sanitizedValue.trim() && !rules.required) {
      return { isValid: true };
    }

    // Length validations
    if (rules.minLength && sanitizedValue.length < rules.minLength) {
      return {
        isValid: false,
        error: `${label} must be at least ${rules.minLength} characters`,
        suggestion: `Current length: ${sanitizedValue.length}. Please add more detail.`
      };
    }

    if (rules.maxLength && sanitizedValue.length > rules.maxLength) {
      return {
        isValid: false,
        error: `${label} must be ${rules.maxLength} characters or less`,
        suggestion: `Current length: ${sanitizedValue.length}. Please shorten your input.`
      };
    }

    // Pattern validation
    if (rules.pattern && !rules.pattern.test(sanitizedValue)) {
      return this.getPatternError(rules.pattern, label, config.examples);
    }

    // Custom validation
    if (rules.custom) {
      const customError = rules.custom(sanitizedValue);
      if (customError) {
        return {
          isValid: false,
          error: customError
        };
      }
    }

    // Check for warnings (non-blocking issues)
    const warning = this.getFieldWarning(sanitizedValue, config);

    return {
      isValid: true,
      warning: warning || undefined
    };
  }

  private getPatternError(pattern: RegExp, label: string, examples?: string[]): ValidationResult {
    // URL pattern
    if (pattern.source.includes('https?')) {
      return {
        isValid: false,
        error: 'Please enter a valid URL starting with http:// or https://',
        suggestion: examples?.[0] || 'Example: https://example.com'
      };
    }

    // Title pattern (alphanumeric with spaces, hyphens, underscores)
    if (pattern.source.includes('a-zA-Z0-9')) {
      return {
        isValid: false,
        error: `${label} can only contain letters, numbers, spaces, hyphens, and underscores`,
        suggestion: 'Avoid special characters like @, #, $, %, etc.'
      };
    }

    return {
      isValid: false,
      error: `${label} format is invalid`
    };
  }

  private getFieldWarning(value: string, config: FieldValidationConfig): string | null {
    // Check for very short descriptions that might not be detailed enough
    if (config.label.toLowerCase().includes('description') && value.length < 100) {
      return 'Consider adding more detail for better AI generation results';
    }

    // Check for URLs without HTTPS
    if (config.label.toLowerCase().includes('url') && value.startsWith('http://')) {
      return 'Consider using HTTPS for better security';
    }

    // Check for overly simple titles
    if (config.label.toLowerCase().includes('title') && value.split(' ').length < 3) {
      return 'More descriptive titles help organize your test cases';
    }

    return null;
  }

  // Get helpful hints for a field
  getFieldHints(config: FieldValidationConfig, currentValue: string = ''): string[] {
    const hints: string[] = [...(config.hints || [])];

    // Dynamic hints based on current state
    if (config.rules.maxLength) {
      const remaining = config.rules.maxLength - currentValue.length;
      if (remaining < 50 && remaining > 0) {
        hints.push(`${remaining} characters remaining`);
      }
    }

    if (config.rules.minLength && currentValue.length < config.rules.minLength) {
      const needed = config.rules.minLength - currentValue.length;
      hints.push(`${needed} more characters needed`);
    }

    return hints;
  }

  // Validate entire form
  validateForm(formData: Record<string, string>, configs: Record<string, FieldValidationConfig>): {
    isValid: boolean;
    errors: Record<string, string>;
    warnings: Record<string, string>;
  } {
    const errors: Record<string, string> = {};
    const warnings: Record<string, string> = {};

    for (const [field, config] of Object.entries(configs)) {
      const value = formData[field] || '';
      const result = this.validateField(value, config);

      if (!result.isValid && result.error) {
        errors[field] = result.error;
      }

      if (result.warning) {
        warnings[field] = result.warning;
      }
    }

    return {
      isValid: Object.keys(errors).length === 0,
      errors,
      warnings
    };
  }
}

// Field configurations for User Journey Wizard
export const WIZARD_FIELD_CONFIGS: Record<string, FieldValidationConfig> = {
  title: {
    rules: {
      required: true,
      maxLength: 200,
      pattern: /^[a-zA-Z0-9\s\-_]+$/,
      custom: (value: string) => {
        // Check for meaningful content
        if (value.trim().length < 3) {
          return 'Title should be at least 3 characters long';
        }
        
        // Check for excessive repetition
        const words = value.toLowerCase().split(/\s+/);
        const uniqueWords = new Set(words);
        if (words.length > 3 && uniqueWords.size < words.length * 0.5) {
          return 'Title contains too much repetition';
        }
        
        return null;
      }
    },
    label: 'Use Case Title',
    description: 'A descriptive name for your test case',
    examples: [
      'User Login Flow Test',
      'E-commerce Checkout Process',
      'Contact Form Submission',
      'Product Search and Filter'
    ],
    hints: [
      'Use descriptive names that clearly identify the test purpose',
      'Avoid special characters except hyphens and underscores',
      'Keep it concise but informative'
    ]
  },
  startingUrl: {
    rules: {
      required: true,
      pattern: /^https?:\/\/.+/,
      custom: (value: string) => {
        try {
          const url = new URL(value);
          
          // Check for localhost or development URLs
          if (url.hostname === 'localhost' || url.hostname.includes('127.0.0.1')) {
            return null; // Allow localhost for development
          }
          
          // Check for suspicious domains
          if (url.hostname.includes('..') || url.hostname.length < 3) {
            return 'URL appears to be invalid or suspicious';
          }
          
          return null;
        } catch {
          return 'Please enter a valid URL';
        }
      }
    },
    label: 'Starting URL',
    description: 'The URL where your user journey begins',
    examples: [
      'https://example.com/login',
      'https://myapp.com/dashboard',
      'https://shop.example.com',
      'https://localhost:3000/app'
    ],
    hints: [
      'Include the full URL with http:// or https://',
      'Make sure the URL is accessible and loads correctly',
      'Use the exact URL where the test should start'
    ]
  },
  userJourney: {
    rules: {
      required: true,
      minLength: 50,
      maxLength: 2000,
      custom: (value: string) => {
        // Check for meaningful content
        const words = value.trim().split(/\s+/);
        if (words.length < 10) {
          return 'User journey should contain more detailed steps';
        }
        
        // Check for action words that indicate a good user journey
        const actionWords = ['click', 'enter', 'navigate', 'select', 'submit', 'verify', 'check', 'fill', 'choose', 'confirm'];
        const hasActions = actionWords.some(word => 
          value.toLowerCase().includes(word)
        );
        
        if (!hasActions) {
          return 'User journey should include specific actions (click, enter, navigate, etc.)';
        }
        
        return null;
      }
    },
    label: 'User Journey Description',
    description: 'Describe the complete user journey step by step',
    examples: [
      'User navigates to login page, enters email and password, clicks login button, and should be redirected to dashboard with welcome message displayed',
      'User searches for a product, filters by price range, adds item to cart, proceeds to checkout, enters shipping information, and completes payment',
      'User fills out contact form with name, email, and message, submits the form, and receives confirmation message'
    ],
    hints: [
      'Include specific actions the user will take',
      'Describe expected outcomes and validations',
      'Mention specific UI elements when possible',
      'Include error scenarios if relevant',
      'Be as detailed as possible for better AI generation'
    ]
  }
};

export const validationManager = ValidationManager.getInstance();