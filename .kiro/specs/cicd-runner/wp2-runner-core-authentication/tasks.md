# Implementation Plan: Runner Core & Authentication

## Overview

This implementation plan breaks down the CI/CD runner core into discrete coding tasks. The runner is a Python CLI application that authenticates with OAuth client credentials, fetches test suite definitions, and creates execution records via the Platform API.

The implementation follows a bottom-up approach: build foundational components (errors, configuration, token cache) first, then authentication layer, then API client layer, then CLI interface, and finally wire everything together in the main runner.

---

## Tasks

- [x] 1. Set up project structure and dependencies
  - Create directory structure: src/, tests/, with all subdirectories
  - Create requirements.txt with: requests>=2.31.0, python-dotenv>=1.0.0, pydantic>=2.5.0, click>=8.1.7
  - Create requirements-dev.txt with: pytest>=7.4.0, pytest-mock>=3.12.0, hypothesis>=6.92.0, responses>=0.24.0, coverage>=7.3.0
  - Create setup.py for package installation
  - Create .gitignore with: .token_cache.json, .env, __pycache__/, *.pyc, .pytest_cache/
  - _Requirements: US1, US2, US3, US4_

- [x] 2. Implement custom exceptions
  - [x] 2.1 Create src/utils/errors.py with custom exception classes
    - Implement RunnerError base exception
    - Implement AuthenticationError with message field
    - Implement APIError with status_code and response fields
    - Implement ConfigurationError with message field
    - _Requirements: US1.5, US4.5_
  
  - [ ]* 2.2 Write unit tests for custom exceptions
    - Test exception instantiation and message formatting
    - Test APIError includes status_code and response
    - _Requirements: US1.5, US4.5_

- [x] 3. Implement configuration management
  - [x] 3.1 Create src/config/settings.py with Settings class
    - Use Pydantic BaseModel for validation
    - Define fields: oauth_client_id, oauth_client_secret, oauth_token_endpoint, api_endpoint, log_level
    - Implement from_env() class method to load from environment
    - Validate URLs are HTTPS format
    - Raise ConfigurationError for missing required variables
    - _Requirements: US1.1_
  
  - [ ]* 3.2 Write property test for environment variable parsing
    - **Property 1: Environment Variable Parsing**
    - **Validates: Requirements US1.1**
    - Generate random valid environment variable sets
    - Verify Settings.from_env() parses correctly
  
  - [ ]* 3.3 Write unit tests for configuration edge cases
    - Test missing required variables
    - Test invalid URL formats
    - Test default log_level value
    - _Requirements: US1.1_

- [x] 4. Implement token cache
  - [x] 4.1 Create src/auth/token_cache.py with TokenCache class
    - Implement __init__ with cache_file parameter (default: .token_cache.json)
    - Implement get_token() to read from disk, return None if missing/corrupted
    - Implement set_token() to write token with calculated expires_at
    - Implement clear() to delete cache file
    - Handle JSON serialization of datetime objects
    - _Requirements: US1.3_
  
  - [ ]* 4.2 Write property test for token caching round trip
    - **Property 2: Token Caching Round Trip**
    - **Validates: Requirements US1.3**
    - Generate random token responses
    - Verify set_token → get_token preserves access_token
  
  - [ ]* 4.3 Write unit tests for token cache edge cases
    - Test handling corrupted cache file
    - Test handling missing cache file
    - Test clearing cache
    - Test datetime serialization
    - _Requirements: US1.3_

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement OAuth client
  - [x] 6.1 Create src/auth/oauth_client.py with OAuthClient class
    - Implement __init__ with client_id, client_secret, token_endpoint
    - Initialize TokenCache instance
    - Implement get_access_token() to check cache first, then request new token
    - Implement _request_new_token() to POST to Cognito with client credentials
    - Request scopes: api/suite.read, api/suite.write, api/execution.write
    - Implement _is_token_expired() to check expires_at with 5-minute buffer
    - Raise AuthenticationError for HTTP 400, 401, network errors
    - _Requirements: US1.2, US1.3, US1.4, US1.5_
  
  - [ ]* 6.2 Write property test for expired token detection
    - **Property 3: Expired Token Detection**
    - **Validates: Requirements US1.4**
    - Generate tokens with past expiration times
    - Verify _is_token_expired returns True
  
  - [ ]* 6.3 Write property test for fresh token detection
    - **Property 4: Fresh Token Detection**
    - **Validates: Requirements US1.4**
    - Generate tokens with future expiration times (>5 min)
    - Verify _is_token_expired returns False
  
  - [ ]* 6.4 Write property test for authentication error messages
    - **Property 5: Authentication Error Messages**
    - **Validates: Requirements US1.5**
    - Generate various error responses (400, 401, network)
    - Verify AuthenticationError contains descriptive messages
  
  - [ ]* 6.5 Write unit tests for OAuth client
    - Test successful token request (mocked Cognito)
    - Test token caching behavior
    - Test token refresh on expiration
    - Test invalid credentials (401)
    - Test network errors
    - _Requirements: US1.2, US1.3, US1.4, US1.5_

- [x] 7. Implement base API client
  - [x] 7.1 Create src/api/client.py with APIClient class
    - Implement __init__ with base_url and oauth_client
    - Initialize requests.Session
    - Implement _get_headers() to construct Authorization and Content-Type headers
    - Implement get() method for GET requests
    - Implement post() method for POST requests
    - Implement patch() method for PATCH requests
    - Implement _handle_response() to parse JSON and raise APIError for status >= 400
    - _Requirements: US2.1, US2.4, US4.5_
  
  - [ ]* 7.2 Write property test for API request headers
    - **Property 6: API Request Headers**
    - **Validates: Requirements US2.4**
    - Generate random access tokens
    - Verify all methods include Authorization and Content-Type headers
  
  - [ ]* 7.3 Write property test for API error handling
    - **Property 11: API Error Handling**
    - **Validates: Requirements US4.5**
    - Generate various API error responses (400, 403, 404, 500)
    - Verify APIError contains status code and details
  
  - [ ]* 7.4 Write unit tests for API client
    - Test GET request with mocked response
    - Test POST request with mocked response
    - Test PATCH request with mocked response
    - Test error handling for each status code
    - _Requirements: US2.1, US2.4, US4.5_

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement test suite API wrapper
  - [x] 9.1 Create src/api/test_suites.py with TestSuiteAPI class
    - Implement __init__ with APIClient instance
    - Implement get_suite(suite_id) to call GET /test-suites/{id}
    - Implement execute_suite() with suite_id and optional overrides
    - Build request body with trigger_type="ci_runner"
    - Include base_url, variables, region, model_id if provided
    - Call POST /test-suites/{id}/execute
    - Return parsed response
    - _Requirements: US2.1, US4.1, US4.2, US4.3, US4.4_
  
  - [ ]* 9.2 Write property test for execute suite request format
    - **Property 9: Execute Suite Request Format**
    - **Validates: Requirements US4.1, US4.2**
    - Generate random suite IDs
    - Verify POST to correct endpoint with trigger_type="ci_runner"
  
  - [ ]* 9.3 Write property test for CLI overrides in request body
    - **Property 10: CLI Overrides in Request Body**
    - **Validates: Requirements US4.3**
    - Generate random combinations of overrides
    - Verify all provided overrides included in body
  
  - [ ]* 9.4 Write unit tests for test suite API
    - Test get_suite with mocked response
    - Test execute_suite with all overrides
    - Test execute_suite with no overrides
    - Test execute_suite with partial overrides
    - _Requirements: US2.1, US4.1, US4.2, US4.3, US4.4_

- [x] 10. Implement CLI argument parser
  - [x] 10.1 Create src/cli/parser.py with Click command
    - Define @click.command() with all options
    - Add --suite-id (required)
    - Add --base-url (optional)
    - Add --var (optional, multiple, repeatable)
    - Add --region (optional)
    - Add --model-id (optional)
    - Add --verbose (flag)
    - Add --timeout (integer, default 3600)
    - Parse --var arguments into dictionary (split on =)
    - Raise click.BadParameter for invalid --var format
    - Call run_runner() from main module
    - _Requirements: US3.1, US3.2, US3.3, US3.4, US3.5, US3.6_
  
  - [ ]* 10.2 Write property test for variable parsing
    - **Property 7: Variable Parsing from CLI**
    - **Validates: Requirements US3.3**
    - Generate random lists of key=value pairs
    - Verify CLI parser produces correct dictionary
  
  - [ ]* 10.3 Write property test for timeout argument parsing
    - **Property 8: Timeout Argument Parsing**
    - **Validates: Requirements US3.5**
    - Generate random integer values
    - Verify timeout parsed correctly and defaults to 3600
  
  - [ ]* 10.4 Write property test for base URL argument parsing
    - **Property 12: Base URL Argument Parsing**
    - **Validates: Requirements US3.2**
    - Generate random valid URLs
    - Verify base-url parsed correctly and None when omitted
  
  - [ ]* 10.5 Write unit tests for CLI parser
    - Test required suite-id argument
    - Test optional arguments
    - Test variable parsing (valid format)
    - Test variable parsing (invalid format)
    - Test help message display
    - _Requirements: US3.1, US3.2, US3.3, US3.4, US3.5, US3.6_

- [x] 11. Implement logging utility
  - [x] 11.1 Create src/utils/logger.py with logging setup
    - Implement setup_logging(verbose: bool) function
    - Configure logging level based on verbose flag (DEBUG if True, INFO if False)
    - Configure log format with timestamp, level, and message
    - Configure console handler
    - _Requirements: US3.4_
  
  - [ ]* 11.2 Write unit tests for logging setup
    - Test logging level with verbose=True
    - Test logging level with verbose=False
    - _Requirements: US3.4_

- [x] 12. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [-] 13. Implement main runner logic
  - [x] 13.1 Create src/main.py with run_runner function
    - Implement run_runner() with all CLI arguments
    - Load configuration from environment using Settings.from_env()
    - Initialize OAuthClient with credentials and token endpoint
    - Call oauth_client.get_access_token() to authenticate
    - Log authentication success
    - Initialize APIClient with base_url and oauth_client
    - Initialize TestSuiteAPI with api_client
    - Call test_suite_api.get_suite(suite_id)
    - Log test suite name
    - Call test_suite_api.execute_suite() with all overrides
    - Extract suite_execution_id and execution_ids from response
    - Log suite_execution_id and count of execution_ids
    - Exit with code 0 on success
    - Catch all exceptions, log error, exit with code 2
    - _Requirements: US1.1, US1.2, US2.1, US4.1, US4.2, US4.3, US4.4_
  
  - [ ]* 13.2 Write integration tests for main runner
    - Test successful execution flow (mocked dependencies)
    - Test authentication failure handling
    - Test API failure handling
    - Test configuration error handling
    - _Requirements: US1.1, US1.2, US2.1, US4.1, US4.2, US4.3, US4.4_

- [-] 14. Wire CLI to main runner
  - [x] 14.1 Update src/cli/parser.py to import and call run_runner
    - Import run_runner from src.main
    - Call setup_logging(verbose) before run_runner
    - Pass all parsed arguments to run_runner
    - _Requirements: US3.1, US3.2, US3.3, US3.4, US3.5, US3.6_
  
  - [x] 14.2 Create src/__init__.py and all submodule __init__.py files
    - Create empty __init__.py in: src/, src/auth/, src/api/, src/cli/, src/config/, src/utils/
    - _Requirements: All_

- [x] 15. Create package setup and documentation
  - [x] 15.1 Create setup.py for package installation
    - Define package metadata (name, version, author)
    - Define entry point: cicd-runner = src.cli.parser:main
    - Define install_requires from requirements.txt
    - Define python_requires >= 3.9
    - _Requirements: All_
  
  - [x] 15.2 Create README.md with usage instructions
    - Document installation steps
    - Document required environment variables
    - Document CLI usage with examples
    - Document OAuth client creation process
    - Include troubleshooting section
    - _Requirements: All_
  
  - [x] 15.3 Create .env.example with template environment variables
    - Include all required variables with placeholder values
    - Include comments explaining each variable
    - _Requirements: US1.1_

- [x] 16. Final checkpoint - Run all tests and verify coverage
  - Run pytest with coverage report
  - Verify coverage >= 70%
  - Run all property tests with 100 iterations
  - Ensure all tests pass
  - Ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional test-related sub-tasks and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at reasonable breaks
- Property tests validate universal correctness properties across many generated inputs
- Unit tests validate specific examples, edge cases, and error conditions
- Integration tests validate end-to-end workflows with mocked external dependencies
- The implementation follows a bottom-up approach: foundational components first, then higher-level components
- All code should follow Python best practices: type hints, docstrings, PEP 8 formatting
- Use `responses` library to mock HTTP requests in tests
- Use `hypothesis` library for property-based tests with @given decorators
- Each property test should run minimum 100 iterations (hypothesis default)

