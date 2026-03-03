import { errorManager, ErrorManager, ERROR_CATEGORIES } from '../errorManager';

describe('ErrorManager', () => {
  beforeEach(() => {
    errorManager.clearHistory();
  });

  describe('createError', () => {
    it('should create error with correct properties', () => {
      const error = errorManager.createError('validation', 'Test error message');
      
      expect(error.type).toBe('validation');
      expect(error.message).toBe('Test error message');
      expect(error.retryable).toBe(false); // validation errors are not retryable
      expect(error.retryCount).toBe(0);
      expect(error.timestamp).toBeGreaterThan(0);
    });

    it('should set retryable based on error type', () => {
      const networkError = errorManager.createError('network', 'Network failed');
      expect(networkError.retryable).toBe(true);

      const validationError = errorManager.createError('validation', 'Invalid input');
      expect(validationError.retryable).toBe(false);

      const bedrockError = errorManager.createError('bedrock', 'AI service failed');
      expect(bedrockError.retryable).toBe(true);
    });
  });

  describe('categorizeHttpError', () => {
    it('should categorize 401 as authentication error', () => {
      const error = errorManager.categorizeHttpError(401, 'Unauthorized');
      expect(error.type).toBe('authentication');
      expect(error.message).toBe('Unauthorized');
    });

    it('should categorize 429 as rate limit error', () => {
      const error = errorManager.categorizeHttpError(429);
      expect(error.type).toBe('rate_limit');
      expect(error.retryable).toBe(true);
    });

    it('should categorize 500+ as network error', () => {
      const error = errorManager.categorizeHttpError(502, 'Bad Gateway');
      expect(error.type).toBe('network');
      expect(error.retryable).toBe(true);
    });

    it('should categorize 400-499 as validation error', () => {
      const error = errorManager.categorizeHttpError(400, 'Bad Request');
      expect(error.type).toBe('validation');
      expect(error.retryable).toBe(false);
    });
  });

  describe('canRetry', () => {
    it('should allow retry for retryable errors under max attempts', () => {
      const error = errorManager.createError('network', 'Connection failed', { maxRetries: 3 });
      expect(errorManager.canRetry(error)).toBe(true);
    });

    it('should not allow retry for non-retryable errors', () => {
      const error = errorManager.createError('validation', 'Invalid input');
      expect(errorManager.canRetry(error)).toBe(false);
    });

    it('should not allow retry when max attempts reached', () => {
      const error = errorManager.createError('network', 'Connection failed', { maxRetries: 2 });
      error.retryCount = 2;
      expect(errorManager.canRetry(error)).toBe(false);
    });
  });

  describe('getUserFriendlyMessage', () => {
    it('should return user-friendly messages for different error types', () => {
      const networkError = errorManager.createError('network', 'TCP connection failed');
      const friendlyMessage = errorManager.getUserFriendlyMessage(networkError);
      expect(friendlyMessage).toBe('Connection failed. Please check your internet and try again.');

      const bedrockError = errorManager.createError('bedrock', 'Model unavailable');
      const bedrockMessage = errorManager.getUserFriendlyMessage(bedrockError);
      expect(bedrockMessage).toBe('The AI service is temporarily busy. Please try again in a moment.');
    });

    it('should return original message for validation errors', () => {
      const validationError = errorManager.createError('validation', 'Email is required');
      const message = errorManager.getUserFriendlyMessage(validationError);
      expect(message).toBe('Email is required');
    });
  });

  describe('getErrorSuggestions', () => {
    it('should return appropriate suggestions for each error type', () => {
      const networkError = errorManager.createError('network', 'Connection failed');
      const suggestions = errorManager.getErrorSuggestions(networkError);
      
      expect(suggestions).toContain('Check your internet connection');
      expect(suggestions).toContain('Try refreshing the page');
    });

    it('should return validation suggestions for validation errors', () => {
      const validationError = errorManager.createError('validation', 'Invalid input');
      const suggestions = errorManager.getErrorSuggestions(validationError);
      
      expect(suggestions).toContain('Check that all required fields are filled out');
    });
  });

  describe('getRetryDelay', () => {
    it('should calculate exponential backoff correctly', () => {
      expect(errorManager.getRetryDelay(0)).toBe(1000); // 1s
      expect(errorManager.getRetryDelay(1)).toBe(2000); // 2s
      expect(errorManager.getRetryDelay(2)).toBe(4000); // 4s
      expect(errorManager.getRetryDelay(3)).toBe(8000); // 8s (max)
      expect(errorManager.getRetryDelay(4)).toBe(8000); // Still 8s (capped)
    });
  });

  describe('error categories', () => {
    it('should have all required error categories defined', () => {
      const requiredTypes = ['validation', 'network', 'bedrock', 'import', 'authentication', 'rate_limit', 'unknown'];
      
      requiredTypes.forEach(type => {
        expect(ERROR_CATEGORIES[type as keyof typeof ERROR_CATEGORIES]).toBeDefined();
        expect(ERROR_CATEGORIES[type as keyof typeof ERROR_CATEGORIES].title).toBeTruthy();
        expect(ERROR_CATEGORIES[type as keyof typeof ERROR_CATEGORIES].suggestions).toBeInstanceOf(Array);
      });
    });
  });
});