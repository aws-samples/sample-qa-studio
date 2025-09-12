import { validationManager, WIZARD_FIELD_CONFIGS } from '../validation';

describe('ValidationManager', () => {
  describe('sanitizeInput', () => {
    it('should preserve whitespace during input sanitization', () => {
      // Light sanitization should preserve spaces
      const input = 'User  Login   Flow';
      const result = validationManager.sanitizeInput(input);
      expect(result).toBe('User  Login   Flow');
    });

    it('should remove dangerous XSS content', () => {
      const input = 'Title <script>alert("xss")</script> Test';
      const result = validationManager.sanitizeInput(input);
      expect(result).toBe('Title  Test');
    });
  });

  describe('sanitizeForValidation', () => {
    it('should normalize whitespace for validation', () => {
      const input = 'User  Login   Flow';
      const result = validationManager.sanitizeForValidation(input);
      expect(result).toBe('User Login Flow');
    });

    it('should trim whitespace for validation', () => {
      const input = '  User Login Flow  ';
      const result = validationManager.sanitizeForValidation(input);
      expect(result).toBe('User Login Flow');
    });
  });

  describe('validateField', () => {
    it('should validate title field correctly', () => {
      const config = WIZARD_FIELD_CONFIGS.title;
      
      // Valid title
      const validResult = validationManager.validateField('Valid Test Title', config);
      expect(validResult.isValid).toBe(true);
      
      // Valid title with multiple spaces
      const spacesResult = validationManager.validateField('User Login Flow Test', config);
      expect(spacesResult.isValid).toBe(true);
      
      // Valid title with hyphens and underscores
      const hyphenResult = validationManager.validateField('User-Login_Flow Test', config);
      expect(hyphenResult.isValid).toBe(true);
      
      // Empty title
      const emptyResult = validationManager.validateField('', config);
      expect(emptyResult.isValid).toBe(false);
      expect(emptyResult.error).toContain('required');
      
      // Too long title
      const longTitle = 'a'.repeat(201);
      const longResult = validationManager.validateField(longTitle, config);
      expect(longResult.isValid).toBe(false);
      expect(longResult.error).toContain('200 characters');
      
      // Invalid characters
      const invalidResult = validationManager.validateField('Title with @#$%', config);
      expect(invalidResult.isValid).toBe(false);
      expect(invalidResult.error).toContain('letters, numbers');
    });

    it('should validate URL field correctly', () => {
      const config = WIZARD_FIELD_CONFIGS.startingUrl;
      
      // Valid URLs
      const validHttps = validationManager.validateField('https://example.com', config);
      expect(validHttps.isValid).toBe(true);
      
      const validHttp = validationManager.validateField('http://localhost:3000', config);
      expect(validHttp.isValid).toBe(true);
      
      // Invalid URLs
      const noProtocol = validationManager.validateField('example.com', config);
      expect(noProtocol.isValid).toBe(false);
      
      const invalidProtocol = validationManager.validateField('ftp://example.com', config);
      expect(invalidProtocol.isValid).toBe(false);
      
      // Empty URL
      const emptyUrl = validationManager.validateField('', config);
      expect(emptyUrl.isValid).toBe(false);
    });

    it('should validate user journey field correctly', () => {
      const config = WIZARD_FIELD_CONFIGS.userJourney;
      
      // Valid journey
      const validJourney = 'User navigates to login page, enters email and password, clicks login button, and should be redirected to dashboard';
      const validResult = validationManager.validateField(validJourney, config);
      expect(validResult.isValid).toBe(true);
      
      // Too short
      const shortJourney = 'User clicks button';
      const shortResult = validationManager.validateField(shortJourney, config);
      expect(shortResult.isValid).toBe(false);
      expect(shortResult.error).toContain('50 characters');
      
      // No action words
      const noActions = 'This is a very long description that does not contain any action words and should fail validation because it lacks specific user interactions';
      const noActionResult = validationManager.validateField(noActions, config);
      expect(noActionResult.isValid).toBe(false);
      expect(noActionResult.error).toContain('actions');
    });
  });

  describe('checkSecurity', () => {
    it('should detect XSS attempts', () => {
      const xssAttempt = '<script>alert("xss")</script>';
      const result = validationManager.checkSecurity(xssAttempt);
      expect(result.isValid).toBe(false);
    });

    it('should detect SQL injection attempts', () => {
      const sqlInjection = "'; DROP TABLE users; --";
      const result = validationManager.checkSecurity(sqlInjection);
      expect(result.isValid).toBe(false);
    });

    it('should allow safe content', () => {
      const safeContent = 'This is a normal user journey description with safe content';
      const result = validationManager.checkSecurity(safeContent);
      expect(result.isValid).toBe(true);
    });
  });

  describe('sanitizeInput', () => {
    it('should remove dangerous characters', () => {
      const dangerous = 'Normal text\x00with\x01control\x02characters';
      const sanitized = validationManager.sanitizeInput(dangerous);
      expect(sanitized).toBe('Normal text with control characters');
    });

    it('should normalize whitespace', () => {
      const messy = '  Multiple   spaces\t\tand\n\ntabs  ';
      const sanitized = validationManager.sanitizeInput(messy);
      expect(sanitized).toBe('Multiple spaces and tabs');
    });
  });

  describe('validateForm', () => {
    it('should validate entire form correctly', () => {
      const validFormData = {
        title: 'Valid Test Case',
        startingUrl: 'https://example.com',
        userJourney: 'User navigates to the page, clicks the login button, enters credentials, and submits the form successfully'
      };

      const result = validationManager.validateForm(validFormData, WIZARD_FIELD_CONFIGS);
      expect(result.isValid).toBe(true);
      expect(Object.keys(result.errors)).toHaveLength(0);
    });

    it('should return errors for invalid form', () => {
      const invalidFormData = {
        title: '',
        startingUrl: 'invalid-url',
        userJourney: 'Too short'
      };

      const result = validationManager.validateForm(invalidFormData, WIZARD_FIELD_CONFIGS);
      expect(result.isValid).toBe(false);
      expect(Object.keys(result.errors)).toHaveLength(3);
    });
  });
});