# Requirements Document

## Introduction

Merge the two separate CLI packages (`qa-studio-cli` and `qa-studio-ci-runner`) into a single unified `qa-studio` CLI package. Currently, both tools share configuration (`~/.qa-studio/config.json`), authentication patterns (token files, OAuth), and API client patterns but maintain separate codebases with duplicated models, error classes, and API clients. The ci-runner already depends on the CLI's config file. Unifying them reduces maintenance burden, eliminates code duplication, and provides a single entry point (`qa-studio`) for all operations — from interactive test management to headless CI execution.

The ci-runner has heavy dependencies (Nova Act, Playwright, boto3) that are not needed for interactive CLI usage. The unified package uses an optional extras install strategy (`pip install qa-studio[runner]`) so lightweight environments only pull in the core dependencies while CI/Docker environments opt into the runner extras.

## Glossary

- **Unified_CLI**: The single merged Click-based CLI application exposed as the `qa-studio` console script
- **Core_Package**: The base `qa-studio` Python package containing config, auth, API client, models, commands, and skills — installable without heavy runner dependencies
- **Runner_Extra**: The optional `[runner]` extras group that adds Nova Act, Playwright, and boto3 dependencies required for local test execution
- **Runner_Command**: The `qa-studio run` Click command group that replaces the standalone `qa-studio-ci-runner` entry point
- **Config_Module**: The shared configuration management module reading/writing `~/.qa-studio/config.json`
- **Auth_Module**: The unified authentication module supporting both browser-based OAuth (PKCE) for interactive use and client-credentials / token-file flows for CI
- **API_Client**: The unified HTTP client for QA Studio API requests with authentication
- **Execution_Engine**: The Nova Act-based test execution engine that runs usecases locally with browser automation
## Requirements

### Requirement 1: Unified Package Structure

**User Story:** As a developer, I want a single Python package that contains all CLI functionality, so that I can install and maintain one tool instead of two.

#### Acceptance Criteria

1. THE Unified_CLI SHALL expose a single `qa-studio` console script entry point via `setup.py` / `pyproject.toml`
2. THE Core_Package SHALL be installable with `pip install qa-studio` using only lightweight dependencies (click, requests, pydantic)
3. THE Runner_Extra SHALL be installable with `pip install qa-studio[runner]` adding Nova Act, Playwright, and boto3 dependencies
4. THE Core_Package SHALL use the Python package name `qa_studio_cli` as the top-level importable module
5. WHEN `pip install qa-studio` is run without the runner extra, THE Core_Package SHALL provide all commands except `qa-studio run`

### Requirement 2: Unified Command Structure

**User Story:** As a CLI user, I want a single command hierarchy for all operations, so that I have one consistent interface for test management and execution.

#### Acceptance Criteria

1. THE Unified_CLI SHALL provide the `configure` command for interactive setup of API URL, Cognito domain, and client ID
2. THE Unified_CLI SHALL provide the `login` command for browser-based OAuth authentication
3. THE Unified_CLI SHALL provide the `logout` command for deleting stored tokens
4. THE Unified_CLI SHALL provide the `tests` command group with `list`, `get`, `create`, `run`, and `delete` subcommands
5. THE Unified_CLI SHALL provide the `suites` command group with `list`, `get`, `create`, `add-tests`, `remove-test`, and `run` subcommands
6. THE Unified_CLI SHALL provide the `run` command for local Nova Act execution with `--usecase-id` and `--suite-id` options
7. THE Unified_CLI SHALL provide the `skills` command group with `list` and `show` subcommands
8. THE Unified_CLI SHALL provide the `setup`, `uninstall`, and `status` commands for skill and auth management

### Requirement 3: Runner Command Integration

**User Story:** As a CI engineer, I want to use `qa-studio run` instead of `qa-studio-ci-runner`, so that I use the same tool in CI as in development.

#### Acceptance Criteria

1. THE Runner_Command SHALL accept `--usecase-id` and `--suite-id` as mutually exclusive options for selecting execution target
2. THE Runner_Command SHALL accept `--local-only` flag for execution without remote state tracking
3. THE Runner_Command SHALL accept `--token-file` for authentication via pre-existing token JSON file
4. THE Runner_Command SHALL accept `--base-url`, `--var`, `--region`, `--model-id`, `--timeout`, `--keep-artifacts`, `--verbose`, and `--format` options matching the current ci-runner interface
5. WHEN the Runner_Extra is not installed and a user invokes `qa-studio run`, THE Unified_CLI SHALL display a clear error message instructing the user to install with `pip install qa-studio[runner]`
6. THE Runner_Command SHALL use Click for argument parsing, replacing the current argparse implementation

### Requirement 4: Shared Configuration Module

**User Story:** As a user, I want both interactive and CI workflows to use the same configuration, so that I configure once and use everywhere.

#### Acceptance Criteria

1. THE Config_Module SHALL read and write configuration to `~/.qa-studio/config.json`
2. THE Config_Module SHALL support environment variable overrides for `api_url` (`QA_STUDIO_API_URL`), `cognito_domain` (`QA_STUDIO_COGNITO_DOMAIN`), and `client_id` (`QA_STUDIO_CLIENT_ID`)
3. THE Config_Module SHALL validate that `api_url` and `cognito_domain` use HTTPS protocol
4. THE Config_Module SHALL set file permissions to `0o600` on the config file after writing
5. THE Config_Module SHALL be used by both interactive commands and the runner command for API endpoint resolution
6. THE Config_Module SHALL support optional `oauth_client_id`, `oauth_client_secret`, and `oauth_token_endpoint` fields in `~/.qa-studio/config.json` for M2M client-credentials authentication
7. THE `configure` command SHALL prompt for the optional M2M OAuth fields (client ID, client secret, token endpoint) after the core fields, allowing the user to skip them for interactive-only usage

### Requirement 5: Unified Authentication Module

**User Story:** As a user, I want a single auth module that handles both interactive login and CI token flows, so that authentication logic is not duplicated.

#### Acceptance Criteria

1. THE Auth_Module SHALL support browser-based OAuth authorization code grant with PKCE for interactive login
2. THE Auth_Module SHALL support client-credentials OAuth flow using credentials from `~/.qa-studio/config.json` (`oauth_client_id`, `oauth_client_secret`, `oauth_token_endpoint`), with environment variables (`OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `OAUTH_TOKEN_ENDPOINT`) as overrides
3. THE Auth_Module SHALL support token-file authentication by reading `access_token` from a JSON file specified via `--token-file`
4. THE Auth_Module SHALL persist tokens to `~/.qa-studio/token.json` with `0o600` file permissions after browser-based login
5. THE Auth_Module SHALL automatically refresh expired tokens using the stored refresh token before falling back to re-authentication
6. WHEN a token file is re-read on each access, THE Auth_Module SHALL pick up externally refreshed tokens without restart
7. WHEN the runner command is invoked without `--token-file` and without env vars, THE Auth_Module SHALL fall back to client credentials from `~/.qa-studio/config.json` if present

### Requirement 6: Unified API Client

**User Story:** As a developer, I want a single API client implementation, so that HTTP request handling, error mapping, and authentication are consistent across all commands.

#### Acceptance Criteria

1. THE API_Client SHALL send authenticated requests with `Authorization: Bearer` headers
2. THE API_Client SHALL map HTTP 401 responses to an actionable "session expired" error message
3. THE API_Client SHALL map HTTP 403 responses to an "insufficient permissions" error message including server-provided detail
4. THE API_Client SHALL map HTTP 404 responses to a "resource not found" error message
5. THE API_Client SHALL support GET, POST, PATCH, and DELETE HTTP methods
6. THE API_Client SHALL be used by both interactive commands and the runner command

### Requirement 7: Unified Pydantic Models and Error Classes

**User Story:** As a developer, I want a single set of data models and error classes, so that there is no duplication between the CLI and runner codebases.

#### Acceptance Criteria

1. THE Core_Package SHALL define a single `CLIConfig` pydantic model for configuration
2. THE Core_Package SHALL define a single `TokenData` pydantic model for persisted tokens
3. THE Core_Package SHALL define a single set of API response models (`UsecaseModel`, `SuiteModel`, `StepModel`, etc.)
4. THE Core_Package SHALL define a single error class hierarchy (`AuthError`, `ConfigError`, `ApiError`) used by all commands
5. THE Core_Package SHALL define execution-specific models (`LocalExecutionResult`, `RemoteExecutionResult`, `StepResultDetail`) in a runner-specific models module
6. WHEN the runner extra is not installed, THE Core_Package SHALL not import runner-specific models at module load time

### Requirement 8: Docker Image Update

**User Story:** As a DevOps engineer, I want the Docker image to use the unified package, so that container-based CI uses the merged tool.

#### Acceptance Criteria

1. THE Dockerfile SHALL install the unified package with runner extras: `pip install qa-studio[runner]`
2. THE Dockerfile SHALL use `qa-studio run` as the container entrypoint
3. THE Dockerfile SHALL maintain the existing multi-stage build pattern with builder and runtime stages

### Requirement 9: Lazy Import for Runner Dependencies

**User Story:** As a developer using the lightweight CLI, I want runner-heavy dependencies to only be imported when the `run` command is invoked, so that the CLI starts fast and works without Nova Act installed.

#### Acceptance Criteria

1. WHEN the `qa-studio run` command is invoked, THE Unified_CLI SHALL import Nova Act, Playwright, and boto3 dependencies at command execution time rather than at module load time
2. WHEN a user runs any command other than `qa-studio run`, THE Unified_CLI SHALL not attempt to import Nova Act, Playwright, or boto3
3. IF Nova Act is not installed and `qa-studio run` is invoked, THEN THE Unified_CLI SHALL display an error message: "Runner dependencies not installed. Run: pip install qa-studio[runner]"

### Requirement 10: Test Migration

**User Story:** As a developer, I want all existing tests from both packages to pass in the unified package, so that no functionality is lost during the merge.

#### Acceptance Criteria

1. THE Core_Package SHALL include all existing CLI tests (configure, login, tests, suites, skills, API client, OAuth, models)
2. THE Core_Package SHALL include all existing runner tests (engine, artifacts, log capture, execution API, backward compat, smoke tests)
3. THE Core_Package SHALL achieve a minimum of 70% unit test coverage
4. WHEN tests for runner functionality are executed, THE test suite SHALL skip runner-specific tests if the runner extra is not installed

### Requirement 11: Dead Code Removal

**User Story:** As a developer, I want all duplicated and dead code removed after the merge, so that the codebase stays clean and maintainable.

#### Acceptance Criteria

1. WHEN the merge is complete, THE Core_Package SHALL not contain duplicate API client implementations
2. WHEN the merge is complete, THE Core_Package SHALL not contain duplicate error class hierarchies
3. WHEN the merge is complete, THE Core_Package SHALL not contain duplicate configuration loading logic
4. WHEN the merge is complete, THE Core_Package SHALL not contain the subprocess-based runner executor (`qa_studio_cli/runner/executor.py`) since the runner is now in-process
5. WHEN the merge is complete, THE old `qa-studio-ci-runner` package directory SHALL be removable without breaking any functionality
