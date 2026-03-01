# Implementation Plan: WP1 CLI Foundation & Auth

## Overview

Build the `qa-studio-cli` Python package with Click-based CLI, Pydantic data models, OAuth browser-based authentication with PKCE, token lifecycle management, and configuration management. Tasks are ordered by dependency: models/errors → config → token manager → OAuth → CLI commands → wiring → tests.

## Tasks

- [x] 1. Scaffold project structure and package configuration
  - Create `qa-studio-cli/` directory with `setup.py`, `requirements.txt`, `requirements-dev.txt`, `README.md`
  - Create `src/` package with `__init__.py`, `src/auth/__init__.py`, `src/models/__init__.py`, `src/utils/__init__.py`
  - Create `tests/` package with `__init__.py` and `conftest.py`
  - `setup.py` must register `qa-studio` console script entry point pointing to `src.cli:cli`
  - Dependencies: `click>=8.1.7`, `requests>=2.31.0`, `pydantic>=2.5.0`
  - Dev dependencies: `pytest>=7.4.0`, `pytest-mock>=3.12.0`, `hypothesis>=6.92.0`, `coverage>=7.3.0`, `responses>=0.24.0`
  - Python version: `>=3.11`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. Implement Pydantic data models and custom errors
  - [x] 2.1 Create error classes in `src/models/errors.py`
    - Implement `AuthError(Exception)` with `message` attribute
    - Implement `ConfigError(Exception)` with `message` attribute
    - Follow the pattern from `qa-studio-ci-runner/src/utils/errors.py`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

  - [x] 2.2 Create `TokenData` model in `src/models/token.py`
    - Fields: `access_token` (str, non-empty), `refresh_token` (str, non-empty), `expires_at` (int, positive), `token_type` (str, default "Bearer")
    - Add Pydantic v2 validators: reject empty `access_token`/`refresh_token`, reject non-positive `expires_at`
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 2.3 Create `CLIConfig` model in `src/models/config.py`
    - Fields: `api_url` (str), `cognito_domain` (str), `client_id` (str, non-empty)
    - Add `field_validator` for `api_url` and `cognito_domain`: must start with `https://`, strip trailing slashes
    - Follow the `validate_https_url` pattern from `qa-studio-ci-runner/src/config/settings.py`
    - _Requirements: 2.7, 2.8, 2.9, 7.4, 7.5, 7.6_

  - [ ]* 2.4 Write property tests for data models (`tests/test_models.py`)
    - **Property 10: URL validation** — any string not starting with `https://` must raise ValidationError when used as `api_url` or `cognito_domain`
    - **Validates: Requirements 2.7, 7.4, 7.5**
    - **Property 11: Token model validation** — empty strings for `access_token`/`refresh_token` and non-positive `expires_at` must raise ValidationError
    - **Validates: Requirements 7.1, 7.2**
    - **Property 12: Trailing slash normalization** — any valid HTTPS URL with trailing slashes must have them stripped after CLIConfig construction
    - **Validates: Requirement 2.8**

- [x] 3. Implement Config Manager (`src/utils/config.py`)
  - [x] 3.1 Implement `save_config()` and `load_config()`
    - `save_config`: write `CLIConfig` to `~/.qa-studio/config.json` with `0o600` permissions, create directory if missing
    - `load_config`: read file, overlay env vars (`QA_STUDIO_API_URL`, `QA_STUDIO_COGNITO_DOMAIN`, `QA_STUDIO_CLIENT_ID`), return validated `CLIConfig`
    - Raise `ConfigError` when neither file nor env vars provide required values
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 3.2 Implement `config_exists()` and `get_config_value()`
    - `config_exists`: check if config file exists on disk
    - `get_config_value`: return single value with env var precedence
    - _Requirements: 6.1, 6.2_

  - [ ]* 3.3 Write unit tests for Config Manager (`tests/test_config.py`)
    - Test `save_config` creates file with correct JSON and `0o600` permissions
    - Test `load_config` returns `CLIConfig` for valid file
    - Test `load_config` env vars override file values
    - Test `load_config` raises `ConfigError` when nothing available
    - Test `config_exists` returns `True`/`False` based on file presence
    - _Requirements: 2.2, 2.4, 2.5, 2.6_

  - [ ]* 3.4 Write property tests for Config Manager
    - **Property 2: Config persistence round-trip** — for any valid `CLIConfig`, `save_config` then `load_config` (no env vars) returns equal instance
    - **Validates: Requirements 2.2, 2.4**
    - **Property 3: File permissions invariant (config)** — after `save_config`, file has permissions `0o600`
    - **Validates: Requirements 2.2, 8.1**
    - **Property 6: Config env var precedence** — env vars override file values for any field where the env var is set
    - **Validates: Requirements 2.4, 2.5**

- [x] 4. Checkpoint - Ensure models and config tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement Token Manager (`src/auth/token_manager.py`)
  - [x] 5.1 Implement `save_token()`, `load_token()`, `delete_token()`
    - `save_token`: write `TokenData` to `~/.qa-studio/token.json` with `0o600` permissions, create directory if missing
    - `load_token`: return `TokenData` if file exists and valid, `None` if missing, raise `AuthError` if corrupt
    - `delete_token`: remove token file if exists, succeed silently if not
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.12_

  - [x] 5.2 Implement `is_token_expired()` and `get_valid_token()`
    - `is_token_expired`: return `True` if `current_time >= expires_at - 30` (30-second buffer)
    - `get_valid_token`: load → check expiry → refresh if needed → return `access_token`
    - Raise `AuthError("Not authenticated. Run 'qa-studio login'.")` if no token file
    - Raise `AuthError("Session expired. Run 'qa-studio login' to re-authenticate.")` if refresh fails
    - _Requirements: 4.6, 4.7, 4.8, 4.9, 4.10, 4.11_

  - [x] 5.3 Implement `refresh_access_token()`
    - POST to Cognito `/oauth2/token` with `grant_type=refresh_token`
    - On success: return new `TokenData` with computed `expires_at`
    - On `invalid_grant`: raise `AuthError`
    - _Requirements: 4.9, 4.10, 4.11_

  - [ ]* 5.4 Write unit tests for Token Manager (`tests/test_token_manager.py`)
    - Test `save_token` creates file with correct JSON and `0o600` permissions
    - Test `load_token` returns `TokenData` for valid file, `None` for missing, `AuthError` for corrupt
    - Test `is_token_expired` returns correct result based on time vs `expires_at - 30`
    - Test `delete_token` removes file, idempotent on missing
    - Test `get_valid_token` returns cached token when not expired
    - Test `get_valid_token` refreshes and saves when expired
    - Test `get_valid_token` raises `AuthError` when no token file
    - Test `get_valid_token` raises `AuthError` when refresh fails
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12_

  - [ ]* 5.5 Write property tests for Token Manager
    - **Property 1: Token persistence round-trip** — for any valid `TokenData`, `save_token` then `load_token` returns equal instance
    - **Validates: Requirements 4.1, 4.3**
    - **Property 3: File permissions invariant (token)** — after `save_token`, file has permissions `0o600`
    - **Validates: Requirements 4.1, 8.1**
    - **Property 5: Expiry buffer correctness** — `is_token_expired` returns `True` iff `current_time >= expires_at - 30`
    - **Validates: Requirement 4.6**
    - **Property 7: get_valid_token idempotency** — calling `get_valid_token` twice with non-expired token returns same access_token
    - **Validates: Requirement 4.8**
    - **Property 8: Logout completeness** — after `delete_token`, `load_token` returns `None`
    - **Validates: Requirement 4.12**

- [x] 6. Checkpoint - Ensure token manager tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement OAuth Flow (`src/auth/oauth.py`)
  - [x] 7.1 Implement `generate_pkce_pair()`
    - Generate `code_verifier` using `secrets.token_urlsafe(64)`
    - Compute `code_challenge` as `base64url(sha256(code_verifier))` (S256)
    - _Requirements: 3.1, 8.2_

  - [x] 7.2 Implement `exchange_code_for_tokens()`
    - POST to Cognito `/oauth2/token` with authorization code + code_verifier
    - Return validated `TokenData` with `expires_at = now + expires_in`
    - Raise `AuthError` on non-200 response
    - _Requirements: 3.6, 3.7, 3.8_

  - [x] 7.3 Implement `start_oauth_flow()`
    - Start local HTTP server on `localhost:19847` (bind to localhost only, not `0.0.0.0`)
    - Open system browser to Cognito `/authorize` with PKCE params
    - Handle callback: capture code on success, error on failure
    - 120-second timeout, shut down server on completion or failure
    - Handle port-in-use error with descriptive message
    - Handle browser-open failure by displaying URL for manual copy
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.9, 3.10, 3.11, 3.12, 8.3_

  - [ ]* 7.4 Write unit tests for OAuth Flow (`tests/test_oauth.py`)
    - Test `generate_pkce_pair` produces verifier 64+ chars and challenge matches SHA256
    - Test `exchange_code_for_tokens` returns `TokenData` on 200 (mock HTTP)
    - Test `exchange_code_for_tokens` raises `AuthError` on non-200
    - Test `start_oauth_flow` timeout raises `AuthError`
    - Test port-in-use error handling
    - _Requirements: 3.1, 3.6, 3.7, 3.8, 3.9, 3.11, 8.2_

  - [ ]* 7.5 Write property test for PKCE
    - **Property 4: PKCE pair validity** — for any generated pair, `base64url(sha256(code_verifier))` equals `code_challenge`
    - **Validates: Requirements 3.1, 8.2**

- [x] 8. Implement CLI commands and config guard (`src/cli.py`)
  - [x] 8.1 Implement `require_config` decorator
    - Check `config_exists()`, if `False`: print message and `raise SystemExit(1)`
    - Do not execute the wrapped command body when config is missing
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 8.2 Implement `configure` command
    - Interactive prompts for API URL, Cognito domain, client ID (no default for client_id)
    - Validate via `CLIConfig` Pydantic model before saving
    - Save with `save_config()`, display success message with file path
    - Must work without existing configuration
    - _Requirements: 2.1, 5.1, 6.3_

  - [x] 8.3 Implement `login` command
    - Decorate with `@require_config`
    - Load config, call `start_oauth_flow()`, save token with `save_token()`
    - Display "✓ Logged in successfully" and token file path
    - Handle `AuthError` with user-friendly message
    - _Requirements: 5.2, 5.3_

  - [x] 8.4 Implement `logout` command
    - Decorate with `@require_config`
    - Call `delete_token()`, display "✓ Logged out successfully"
    - _Requirements: 5.4, 5.5_

  - [x] 8.5 Implement `status` command
    - Decorate with `@require_config`
    - Call `get_valid_token()` to trigger refresh if needed
    - On success: display "✓ Authenticated" and token expiry timestamp
    - On `AuthError`: display "✗" with the error message
    - _Requirements: 5.6, 5.7, 5.8_

  - [ ]* 8.6 Write unit tests for CLI commands (`tests/test_cli.py`)
    - Test `configure` prompts for values and saves config (use Click `CliRunner`)
    - Test `login` calls OAuth flow and saves token
    - Test `logout` calls `delete_token`
    - Test `status` shows authenticated/not authenticated states
    - Test config guard blocks `login`/`logout`/`status` when config missing (exit code 1)
    - Test config guard does not block `configure`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 6.1, 6.2, 6.3_

  - [ ]* 8.7 Write property test for config guard
    - **Property 9: Config guard enforcement** — when `config_exists()` returns `False`, any decorated command raises `SystemExit(1)` without executing the body
    - **Validates: Requirements 6.1, 6.2**

- [x] 9. Wire everything together and create README
  - [x] 9.1 Wire `src/models/__init__.py` exports and `src/auth/__init__.py` exports
    - Ensure clean import paths: `from src.models.token import TokenData`, etc.
    - Ensure CLI entry point `src.cli:cli` works end-to-end
    - _Requirements: 1.5_

  - [x] 9.2 Create `README.md` with installation and usage instructions
    - Document: install runner first (`pip install -e ./qa-studio-ci-runner`), then CLI (`pip install -e ./qa-studio-cli`)
    - Document: `qa-studio configure`, `qa-studio login`, `qa-studio status`, `qa-studio logout`
    - Document environment variable overrides
    - _Requirements: 1.1, 1.4_

- [x] 10. Final checkpoint - Ensure all tests pass and coverage ≥70%
  - Ensure all tests pass, ask the user if questions arise.
  - Run `pytest --cov=src tests/` and verify ≥70% coverage
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All data models use Pydantic v2, consistent with `qa-studio-ci-runner`
- File permissions `0o600` enforced on all sensitive files (tokens and config)
- The `qa-studio-ci-runner` is a separate pip dependency, not bundled
