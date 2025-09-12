import { ApiError } from './api';

export interface ErrorState {
  type: 'validation' | 'network' | 'bedrock' | 'import' | 'authentication' | 'rate_limit' | 'unknown';
  message: string;
  retryable: boolean;
  details?: string;
  code?: string;
  timestamp: number;
  retryCount: number;
  maxRetries: number;
}

export interface ErrorCategory {
  title: string;
  description: string;
  icon: 'error' | 'warning' | 'info';
  suggestions: string[];
}

export const ERROR_CATEGORIES: Record<ErrorState['type'], ErrorCategory> = {
  validation: {
    title: 'Input Validation Error',
    description: 'There are issues with the information you provided',
    icon: 'warning',
    suggestions: [
      'Check that all required fields are filled out',
      'Ensure URLs start with http:// or https://',
      'Verify that text lengths are within allowed limits'
    ]
  },
  network: {
    title: 'Connection Error',
    description: 'Unable to connect to the service',
    icon: 'error',
    suggestions: [
      'Check your internet connection',
      'Try refreshing the page',
      'Wait a moment and try again'
    ]
  },
  bedrock: {
    title: 'AI Service Error',
    description: 'The AI service is temporarily unavailable',
    icon: 'warning',
    suggestions: [
      'The AI service may be experiencing high demand',
      'Try again in a few moments',
      'Consider simplifying your user journey description'
    ]
  },
  import: {
    title: 'Import Error',
    description: 'Failed to save the generated test case',
    icon: 'error',
    suggestions: [
      'The generated test case may have formatting issues',
      'Try regenerating the use case',
      'Contact support if the problem persists'
    ]
  },
  authentication: {
    title: 'Authentication Error',
    description: 'Your session has expired or is invalid',
    icon: 'error',
    suggestions: [
      'Please refresh the page to sign in again',
      'Check that you have the necessary permissions',
      'Contact your administrator if issues persist'
    ]
  },
  rate_limit: {
    title: 'Rate Limit Exceeded',
    description: 'Too many requests have been made',
    icon: 'warning',
    suggestions: [
      'Please wait a few minutes before trying again',
      'The service has usage limits to ensure quality',
      'Try again after the cooldown period'
    ]
  },
  unknown: {
    title: 'Unexpected Error',
    description: 'An unexpected error occurred',
    icon: 'error',
    suggestions: [
      'Try refreshing the page',
      'Check the browser console for more details',
      'Contact support if the problem persists'
    ]
  }
};

export class ErrorManager {
  private static instance: ErrorManager;
  private errorHistory: ErrorState[] = [];

  static getInstance(): ErrorManager {
    if (!ErrorManager.instance) {
      ErrorManager.instance = new ErrorManager();
    }
    return ErrorManager.instance;
  }

  createError(
    type: ErrorState['type'],
    message: string,
    options: Partial<Pick<ErrorState, 'details' | 'code' | 'retryable' | 'maxRetries'>> = {}
  ): ErrorState {
    const error: ErrorState = {
      type,
      message,
      retryable: options.retryable ?? this.isRetryableByType(type),
      details: options.details,
      code: options.code,
      timestamp: Date.now(),
      retryCount: 0,
      maxRetries: options.maxRetries ?? this.getDefaultMaxRetries(type)
    };

    this.errorHistory.push(error);
    return error;
  }

  enhanceApiError(apiError: ApiError): ErrorState {
    return this.createError(
      apiError.type,
      apiError.message,
      {
        details: apiError.details,
        retryable: apiError.retryable
      }
    );
  }

  categorizeHttpError(status: number, message?: string): ErrorState {
    if (status === 401 || status === 403) {
      return this.createError('authentication', 
        message || 'Authentication failed. Please sign in again.');
    }
    
    if (status === 429) {
      return this.createError('rate_limit', 
        message || 'Rate limit exceeded. Please wait before trying again.');
    }
    
    if (status >= 400 && status < 500) {
      return this.createError('validation', 
        message || 'Invalid request. Please check your input.');
    }
    
    if (status >= 500) {
      return this.createError('network', 
        message || 'Server error. Please try again later.');
    }
    
    return this.createError('unknown', 
      message || 'An unexpected error occurred.');
  }

  canRetry(error: ErrorState): boolean {
    return error.retryable && error.retryCount < error.maxRetries;
  }

  incrementRetryCount(error: ErrorState): ErrorState {
    return {
      ...error,
      retryCount: error.retryCount + 1
    };
  }

  getRetryDelay(retryCount: number): number {
    // Exponential backoff: 1s, 2s, 4s, 8s (max 8s)
    return Math.min(Math.pow(2, retryCount) * 1000, 8000);
  }

  getUserFriendlyMessage(error: ErrorState): string {
    const category = ERROR_CATEGORIES[error.type];
    
    if (error.type === 'validation') {
      return error.message; // Validation messages are already user-friendly
    }
    
    if (error.type === 'bedrock') {
      return 'The AI service is temporarily busy. Please try again in a moment.';
    }
    
    if (error.type === 'network') {
      return 'Connection failed. Please check your internet and try again.';
    }
    
    if (error.type === 'import') {
      return 'Failed to save your test case. Please try regenerating it.';
    }
    
    if (error.type === 'authentication') {
      return 'Your session has expired. Please refresh the page to sign in again.';
    }
    
    if (error.type === 'rate_limit') {
      return 'You\'ve reached the usage limit. Please wait a few minutes before trying again.';
    }
    
    return error.message || category.description;
  }

  getErrorSuggestions(error: ErrorState): string[] {
    return ERROR_CATEGORIES[error.type].suggestions;
  }

  private isRetryableByType(type: ErrorState['type']): boolean {
    switch (type) {
      case 'network':
      case 'bedrock':
      case 'import':
      case 'rate_limit':
        return true;
      case 'validation':
      case 'authentication':
      case 'unknown':
      default:
        return false;
    }
  }

  private getDefaultMaxRetries(type: ErrorState['type']): number {
    switch (type) {
      case 'network':
        return 3;
      case 'bedrock':
        return 2; // Bedrock calls are expensive
      case 'import':
        return 2;
      case 'rate_limit':
        return 1; // Wait for cooldown
      default:
        return 0;
    }
  }

  // Analytics and monitoring
  getErrorStats(): { type: string; count: number }[] {
    const stats = new Map<string, number>();
    
    this.errorHistory.forEach(error => {
      const count = stats.get(error.type) || 0;
      stats.set(error.type, count + 1);
    });
    
    return Array.from(stats.entries()).map(([type, count]) => ({ type, count }));
  }

  clearHistory(): void {
    this.errorHistory = [];
  }
}

export const errorManager = ErrorManager.getInstance();