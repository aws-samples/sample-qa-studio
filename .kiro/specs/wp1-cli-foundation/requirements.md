# Requirements Document

## Introduction

This document defines the requirements for WP1: CLI Foundation & Auth — a standalone Python CLI tool (`qa-studio-cli`) that provides browser-based OAuth authentication against AWS Cognito and token lifecycle management. The CLI exposes four commands (`configure`, `login`, `logout`, `status`), stores configuration and tokens in `~/.qa-studio/`, uses Click for the CLI framework, and Pydantic for all data models. The `qa-studio-ci-runner` is treated as a separate pip dependency.

## Glossary

- **CLI**: The `qa-studio-cli` Click-based command-line interface tool
- **Config_Manager**: The module responsible for loading, saving, and validating configuration in `~/.qa-studio/config.json` with environment variable overrides
- **Token_Manager**: The module responsible for persisting, loading, validating, refreshing, and deleting tokens in `~/.qa-studio/token.json`
- **OAuth_Flow**: The module implementing browser-based OAuth authorization code grant with PKCE against Cognito
- **Cognito**: AWS Cognito hosted UI used as the identity provider for authentication
- **PKCE**: Proof Key for Code Exchange (RFC 7636), a security extension to the OAuth authorization code flow
- **TokenData**: Pydantic model representing persisted token data (access_token, refresh_token, expires_at, token_type)
- **CLIConfig**: Pydantic model representing CLI configuration (api_url, cognito_domain, client_id)
- **Config_Guard**: A decorator that prevents command execution when configuration is missing
- **Callback_Server**: A temporary local HTTP server on `localhost:19847` that captures the OAuth authorization code

## Requirements

### Requirement 1: CLI Project Structure and Installation

**User Story:** As a developer, I want to install the QA Studio CLI via pip, so that I can use it as a standalone command-line tool.

#### Acceptance Criteria

1. THE CLI SHALL be installable via `pip install -e ./qa-studio-cli` as a Python package with entry point `qa-studio`
2. THE CLI SHALL require Python version >=3.11
3. THE CLI SHALL declare `click>=8.1.7`, `requests>=2.31.0`, and `pydantic>=2.5.0` as dependencies
4. THE CLI SHALL treat `qa-studio-ci-runner` as a separate pip dependency that is not bundled in the CLI package
5. THE CLI SHALL register a `qa-studio` console script entry point that invokes the Click command group

### Requirement 2: Configuration Management

**User Story:** As a developer, I want to configure the CLI with my environment-specific settings, so that the CLI can connect to the correct API and Cognito endpoints.

#### Acceptance Criteria

1. WHEN a user runs `qa-studio configure`, THE Config_Manager SHALL interactively prompt for API URL, Cognito domain, and Cognito client ID
2. WHEN saving configuration, THE Config_Manager SHALL write to `~/.qa-studio/config.json` with file permissions `0o600`
3. WHEN the `~/.qa-studio/` directory does not exist, THE Config_Manager SHALL create it before writing the config file
4. WHEN loading configuration, THE Config_Manager SHALL overlay environment variables (`QA_STUDIO_API_URL`, `QA_STUDIO_COGNITO_DOMAIN`, `QA_STUDIO_CLIENT_ID`) over file values
5. WHEN an environment variable is set, THE Config_Manager SHALL use the environment variable value regardless of the file value for that field
6. WHEN neither a config file nor environment variables provide required values, THE Config_Manager SHALL raise a ConfigError with the message "Configuration not found. Run 'qa-studio configure' first."
7. THE CLIConfig model SHALL reject any `api_url` or `cognito_domain` that does not start with `https://`
8. THE CLIConfig model SHALL strip trailing slashes from `api_url` and `cognito_domain`
9. THE CLIConfig model SHALL require `client_id` with no default value

### Requirement 3: OAuth Browser-Based Authentication

**User Story:** As a developer, I want to authenticate via my browser, so that I can securely log in to QA Studio without entering credentials in the terminal.

#### Acceptance Criteria

1. WHEN a user runs `qa-studio login`, THE OAuth_Flow SHALL generate a PKCE code_verifier and code_challenge (S256) pair per RFC 7636
2. WHEN starting the OAuth flow, THE OAuth_Flow SHALL start a temporary HTTP server on `localhost:19847` to receive the callback
3. WHEN the callback server is started, THE OAuth_Flow SHALL open the system browser to the Cognito `/authorize` endpoint with the PKCE code_challenge, client_id, and redirect_uri parameters
4. WHEN Cognito redirects with an authorization code, THE Callback_Server SHALL capture the code and respond with HTTP 200 and a success message
5. WHEN Cognito redirects with an error, THE Callback_Server SHALL capture the error and respond with HTTP 400
6. WHEN the authorization code is captured, THE OAuth_Flow SHALL exchange it for tokens via Cognito's `/oauth2/token` endpoint using the code_verifier
7. WHEN the token exchange succeeds, THE OAuth_Flow SHALL return a validated TokenData Pydantic model with `expires_at` computed as `current_time + expires_in`
8. WHEN the token exchange fails, THE OAuth_Flow SHALL raise an AuthError with the status code and error description
9. IF the user does not complete authentication within 120 seconds, THEN THE OAuth_Flow SHALL raise an AuthError with the message "OAuth flow timed out. No authorization code received."
10. WHEN the OAuth flow completes or fails, THE OAuth_Flow SHALL shut down the callback server
11. IF port 19847 is already in use, THEN THE OAuth_Flow SHALL raise an AuthError with the message "Port 19847 is already in use. Close the application using it and try again."
12. IF the system browser cannot be opened, THEN THE OAuth_Flow SHALL display the authorize URL for the user to open manually

### Requirement 4: Token Persistence and Management

**User Story:** As a developer, I want my authentication tokens to be securely stored and automatically refreshed, so that I don't have to re-authenticate frequently.

#### Acceptance Criteria

1. WHEN saving a token, THE Token_Manager SHALL write the TokenData to `~/.qa-studio/token.json` with file permissions `0o600`
2. WHEN the `~/.qa-studio/` directory does not exist, THE Token_Manager SHALL create it before writing the token file
3. WHEN loading a token, THE Token_Manager SHALL return a validated TokenData Pydantic model if the file exists and contains valid JSON
4. WHEN loading a token and the file does not exist, THE Token_Manager SHALL return None
5. IF the token file contains invalid JSON or missing fields, THEN THE Token_Manager SHALL raise an AuthError with a descriptive message
6. WHEN checking token expiry, THE Token_Manager SHALL consider a token expired if `current_time >= expires_at - 30` (30-second buffer)
7. WHEN `get_valid_token()` is called and no token file exists, THE Token_Manager SHALL raise an AuthError with the message "Not authenticated. Run 'qa-studio login'."
8. WHEN `get_valid_token()` is called and the token is not expired, THE Token_Manager SHALL return the access_token without making any network requests
9. WHEN `get_valid_token()` is called and the token is expired, THE Token_Manager SHALL attempt to refresh the token via Cognito's token endpoint using the refresh_token
10. WHEN a token refresh succeeds, THE Token_Manager SHALL save the new TokenData to disk and return the new access_token
11. IF a token refresh fails with `invalid_grant`, THEN THE Token_Manager SHALL raise an AuthError with the message "Session expired. Run 'qa-studio login' to re-authenticate."
12. WHEN deleting a token, THE Token_Manager SHALL remove the token file if it exists and succeed silently if it does not

### Requirement 5: CLI Commands

**User Story:** As a developer, I want clear CLI commands for authentication lifecycle, so that I can configure, log in, check status, and log out easily.

#### Acceptance Criteria

1. THE CLI SHALL provide a `configure` command that collects API URL, Cognito domain, and client ID interactively and saves the configuration
2. THE CLI SHALL provide a `login` command that starts the OAuth flow and saves the resulting tokens
3. WHEN login succeeds, THE CLI SHALL display "✓ Logged in successfully" and the token file path
4. THE CLI SHALL provide a `logout` command that deletes stored tokens
5. WHEN logout succeeds, THE CLI SHALL display "✓ Logged out successfully"
6. THE CLI SHALL provide a `status` command that shows the current authentication state
7. WHEN the user is authenticated, THE CLI `status` command SHALL display "✓ Authenticated" and the token expiry timestamp
8. WHEN the user is not authenticated, THE CLI `status` command SHALL display "✗ Not authenticated" with guidance to run `qa-studio login`

### Requirement 6: Config Guard

**User Story:** As a developer, I want the CLI to prevent me from running commands before configuration is set up, so that I get clear guidance instead of cryptic errors.

#### Acceptance Criteria

1. WHEN a user runs `login`, `logout`, or `status` without existing configuration, THE Config_Guard SHALL prevent execution and display "Configuration not found. Run 'qa-studio configure' first."
2. WHEN a user runs `login`, `logout`, or `status` without existing configuration, THE Config_Guard SHALL exit with code 1
3. THE `configure` command SHALL execute without requiring existing configuration

### Requirement 7: Data Model Validation

**User Story:** As a developer, I want all data to be validated through Pydantic models, so that invalid data is caught early and consistently.

#### Acceptance Criteria

1. THE TokenData model SHALL reject construction with an empty `access_token` or empty `refresh_token`
2. THE TokenData model SHALL require `expires_at` to be a positive integer
3. THE TokenData model SHALL default `token_type` to "Bearer"
4. THE CLIConfig model SHALL reject `api_url` values that do not start with `https://`
5. THE CLIConfig model SHALL reject `cognito_domain` values that do not start with `https://`
6. THE CLIConfig model SHALL require a non-empty `client_id`

### Requirement 8: Security

**User Story:** As a developer, I want my credentials and tokens to be handled securely, so that sensitive data is not exposed.

#### Acceptance Criteria

1. WHEN writing token or config files, THE CLI SHALL set file permissions to `0o600` (owner read/write only)
2. THE OAuth_Flow SHALL use PKCE (S256) for all authorization code exchanges to prevent code interception
3. THE Callback_Server SHALL bind to `localhost` only and not to `0.0.0.0`
4. THE CLI SHALL not store any client secrets in configuration files (public client only)
5. THE CLI SHALL not log or display token values in any output or error messages

### Requirement 9: Error Handling

**User Story:** As a developer, I want clear and actionable error messages, so that I can quickly resolve issues.

#### Acceptance Criteria

1. IF configuration is missing, THEN THE CLI SHALL display "Configuration not found. Run 'qa-studio configure' first."
2. IF port 19847 is in use, THEN THE CLI SHALL display "Port 19847 is already in use. Close the application using it and try again."
3. IF the OAuth flow times out, THEN THE CLI SHALL display "OAuth flow timed out. No authorization code received."
4. IF token exchange fails, THEN THE CLI SHALL display the HTTP status code and error description from Cognito
5. IF the refresh token is expired or revoked, THEN THE CLI SHALL display "Session expired. Run 'qa-studio login' to re-authenticate."
6. IF the token file is corrupt, THEN THE CLI SHALL display "Corrupt token file:" followed by the parse error details
7. IF a non-HTTPS URL is provided during configuration, THEN THE CLI SHALL display a validation error indicating the URL must start with `https://`

### Requirement 10: Testing

**User Story:** As a developer, I want comprehensive test coverage, so that the CLI behaves correctly and regressions are caught early.

#### Acceptance Criteria

1. THE CLI project SHALL achieve at least 70% unit test coverage across all modules
2. THE test suite SHALL include property-based tests using the `hypothesis` library for token round-trip, config round-trip, PKCE pair validity, and expiry check monotonicity
3. THE test suite SHALL include unit tests for Token_Manager covering save, load, expiry check, refresh, delete, and `get_valid_token` scenarios
4. THE test suite SHALL include unit tests for Config_Manager covering save, load, env var override, validation, and `config_exists` scenarios
5. THE test suite SHALL include unit tests for OAuth_Flow covering PKCE generation, token exchange success and failure, and flow timeout
6. THE test suite SHALL include unit tests for CLI commands covering configure, login, logout, status, and config guard behavior
