# Requirements Document

## Introduction

Enhance the existing `qa-studio-ci-runner` to support single use case execution with both local-only and remote modes, and add token file authentication as an alternative to OAuth client credentials. This enables the QA Studio CLI tool to invoke the runner for interactive developer workflows (local testing against localhost) while preserving the existing suite-based CI/CD execution path.

## Glossary

- **Runner**: The `qa-studio-ci-runner` Python CLI application that executes QA Studio test use cases using Nova Act SDK with a local Chromium browser.
- **CLI_Parser**: The Click-based command-line argument parser in `qa-studio-ci-runner/src/cli/parser.py` that validates and routes CLI input.
- **OAuthClient**: The authentication module in `qa-studio-ci-runner/src/auth/oauth_client.py` that obtains access tokens for API communication.
- **ExecutionEngine**: The component in `qa-studio-ci-runner/src/execution/engine.py` that orchestrates Nova Act test execution for use cases.
- **UseCaseAPI**: A new API client class for fetching use case definitions, steps, variables, and secrets directly from the platform API.
- **APIClient**: The base HTTP client in `qa-studio-ci-runner/src/api/client.py` that handles authenticated requests to the platform API.
- **ExecutionAPI**: The API client in `qa-studio-ci-runner/src/api/executions.py` that manages execution records and status updates.
- **Settings**: The Pydantic-based configuration model in `qa-studio-ci-runner/src/config/settings.py` that loads settings from environment variables.
- **Token_File**: A JSON file at a user-specified path containing an `access_token` field, used as an alternative authentication method to client credentials.
- **Local_Only_Mode**: An execution mode where the Runner fetches use case data from the API but skips creating execution records, uploading artifacts to S3, and updating execution status.
- **Remote_Mode**: The default execution mode where the Runner creates execution records, uploads artifacts, and updates status via the API.
- **CLI_Wrapper**: The module in `qa-studio-cli/src/runner/executor.py` that invokes the Runner as a subprocess from the QA Studio CLI tool.

## Requirements

### Requirement 1: Mutually Exclusive Execution Target Flags

**User Story:** As a developer, I want to execute either a single use case or a full test suite, so that I can run targeted tests during development without executing an entire suite.

#### Acceptance Criteria

1. THE CLI_Parser SHALL accept an optional `--usecase-id` flag that specifies a single use case UUID to execute.
2. THE CLI_Parser SHALL accept an optional `--suite-id` flag that specifies a test suite UUID to execute.
3. WHEN neither `--suite-id` nor `--usecase-id` is provided, THE CLI_Parser SHALL exit with an error message stating that one of the two flags is required.
4. WHEN both `--suite-id` and `--usecase-id` are provided, THE CLI_Parser SHALL exit with an error message stating that the two flags are mutually exclusive.
5. WHEN `--suite-id` is provided without `--usecase-id`, THE Runner SHALL execute the full test suite using the existing `run_runner` function.

### Requirement 2: Local-Only Execution Mode

**User Story:** As a developer, I want to run a use case locally without creating execution records or uploading artifacts, so that I can quickly validate changes against localhost without polluting the platform with test records.

#### Acceptance Criteria

1. THE CLI_Parser SHALL accept an optional `--local-only` boolean flag.
2. WHEN `--local-only` is provided without `--usecase-id`, THE CLI_Parser SHALL exit with an error message stating that `--local-only` requires `--usecase-id`.
3. WHEN `--local-only` is provided with `--usecase-id`, THE Runner SHALL fetch the use case definition, steps, variables, and secrets from the platform API.
4. WHILE in Local_Only_Mode, THE Runner SHALL execute the use case steps locally using Nova Act SDK without creating any execution records in the platform.
5. WHILE in Local_Only_Mode, THE Runner SHALL store artifacts (video recording, logs) in a local directory at `/tmp/qa-studio-artifacts/<usecase-id>/`.
6. WHILE in Local_Only_Mode, THE Runner SHALL skip uploading artifacts to S3.
7. WHILE in Local_Only_Mode, THE Runner SHALL skip updating execution status via the API.
8. WHEN local-only execution completes, THE Runner SHALL output the execution result as JSON to stdout containing status, usecase ID, usecase name, duration, step results, and local artifact paths.
9. WHEN local-only execution succeeds, THE Runner SHALL exit with code 0.
10. WHEN local-only execution fails due to a test failure, THE Runner SHALL exit with code 1.
11. IF an unexpected error occurs during local-only execution, THEN THE Runner SHALL exit with code 2.

### Requirement 3: Remote Single Use Case Execution

**User Story:** As a developer, I want to execute a single use case with full execution tracking, so that I can run individual tests that appear in the platform UI with artifacts and status.

#### Acceptance Criteria

1. WHEN `--usecase-id` is provided without `--local-only`, THE Runner SHALL create an execution record via `POST /usecase/{id}/execute` with trigger type `ci_runner`.
2. WHEN the execution record is created, THE Runner SHALL fetch execution details including steps and variables from the ExecutionAPI.
3. THE Runner SHALL execute the use case steps using Nova Act SDK with the execution details from the API.
4. WHEN execution completes, THE Runner SHALL upload artifacts to S3 via presigned URLs.
5. WHEN execution completes, THE Runner SHALL update the execution status via the API.
6. WHEN remote execution succeeds, THE Runner SHALL exit with code 0.
7. WHEN remote execution fails due to a test failure, THE Runner SHALL exit with code 1.
8. IF an unexpected error occurs during remote execution, THEN THE Runner SHALL exit with code 2.
9. WHEN remote execution completes, THE Runner SHALL output the execution result as JSON to stdout.

### Requirement 4: Token File Authentication

**User Story:** As a developer using the QA Studio CLI, I want to authenticate the runner using a token file generated by `qa-studio login`, so that I can run tests without configuring OAuth client credentials.

#### Acceptance Criteria

1. THE CLI_Parser SHALL accept an optional `--token-file` flag that specifies a file path to a JSON token file.
2. WHEN `--token-file` is provided, THE OAuthClient SHALL read the `access_token` field from the JSON file at the specified path.
3. WHEN `--token-file` is provided, THE OAuthClient SHALL use the token from the file for all API requests instead of performing the client credentials flow.
4. WHEN `--token-file` is provided, THE Settings SHALL not require `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, or `OAUTH_TOKEN_ENDPOINT` environment variables.
5. IF the token file path does not exist, THEN THE OAuthClient SHALL raise a descriptive error including the file path.
6. IF the token file does not contain a valid `access_token` field, THEN THE OAuthClient SHALL raise a descriptive error.
7. WHEN `get_access_token` is called with token file mode, THE OAuthClient SHALL re-read the file on each call to pick up externally refreshed tokens.
8. WHEN neither `--token-file` nor client credential environment variables are configured, THE Runner SHALL exit with code 2 and a descriptive error message.

### Requirement 5: Use Case API Client

**User Story:** As a developer, I want the runner to fetch use case definitions directly from the API, so that single use case execution can retrieve all necessary data without going through the suite execution flow.

#### Acceptance Criteria

1. THE UseCaseAPI SHALL provide a method to fetch use case metadata via `GET /usecase/{id}`.
2. THE UseCaseAPI SHALL provide a method to fetch use case steps via `GET /usecase/{id}/steps`.
3. THE UseCaseAPI SHALL provide a method to fetch use case variables via `GET /usecase/{id}/variables`.
4. THE UseCaseAPI SHALL provide a method to fetch use case secrets via `GET /usecase/{id}/secrets`.
5. THE UseCaseAPI SHALL provide a method to create an execution record via `POST /usecase/{id}/execute` with a trigger type parameter.
6. THE UseCaseAPI SHALL use the existing APIClient for all HTTP requests, inheriting authentication and error handling.
7. IF any API request fails, THEN THE UseCaseAPI SHALL propagate the APIError with the original status code and response body.

### Requirement 6: Variable and URL Override for Single Use Case

**User Story:** As a developer, I want to override the base URL and variables when running a single use case, so that I can test against different environments like localhost.

#### Acceptance Criteria

1. WHEN `--base-url` is provided with `--usecase-id` in Local_Only_Mode, THE Runner SHALL replace the use case starting URL origin with the provided base URL while preserving the path and query parameters.
2. WHEN `--var` overrides are provided with `--usecase-id` in Local_Only_Mode, THE Runner SHALL merge the overrides with the use case variables, with CLI overrides taking precedence.
3. WHEN `--base-url` is provided with `--usecase-id` in Remote_Mode, THE Runner SHALL pass the base URL to the execution creation API for server-side URL transformation.
4. WHEN `--var` overrides are provided with `--usecase-id` in Remote_Mode, THE Runner SHALL pass the variable overrides to the execution creation API for server-side merging.
5. WHEN `--region` is provided with `--usecase-id`, THE Runner SHALL use the specified region for Nova Act browser creation instead of the use case default.
6. WHEN `--model-id` is provided with `--usecase-id`, THE Runner SHALL use the specified model ID for Nova Act execution instead of the use case default.

### Requirement 7: Execution Engine Local-Only Support

**User Story:** As a developer, I want the execution engine to support a local-only execution path, so that use cases can be executed without any remote state management.

#### Acceptance Criteria

1. THE ExecutionEngine SHALL provide an `execute_usecase_local` method that accepts use case metadata, steps, variables, and secrets as input parameters.
2. WHEN `execute_usecase_local` is called, THE ExecutionEngine SHALL execute all steps sequentially using Nova Act SDK.
3. WHEN a step fails during local execution, THE ExecutionEngine SHALL stop execution and return a result with status `failed`.
4. WHEN all steps succeed during local execution, THE ExecutionEngine SHALL return a result with status `success`.
5. THE `execute_usecase_local` method SHALL return a result dictionary containing status, usecase ID, usecase name, duration in seconds, step results, and local artifact file paths.
6. THE `execute_usecase_local` method SHALL create the local artifacts directory at `/tmp/qa-studio-artifacts/<usecase-id>/` if the directory does not exist.

### Requirement 8: CLI Wrapper for QA Studio CLI Integration

**User Story:** As a developer using the QA Studio CLI, I want a wrapper module that invokes the runner as a subprocess, so that `qa-studio run` can execute tests seamlessly.

#### Acceptance Criteria

1. THE CLI_Wrapper SHALL invoke the Runner as a subprocess using `python -m qa_studio_ci_runner` with the appropriate flags.
2. THE CLI_Wrapper SHALL pass the token file path from `~/.qa-studio/token.json` as the `--token-file` argument.
3. THE CLI_Wrapper SHALL pass `--usecase-id` and `--local-only` flags to the Runner subprocess.
4. WHEN `--base-url` is provided to the CLI, THE CLI_Wrapper SHALL forward the value to the Runner subprocess.
5. WHEN `--var` overrides are provided to the CLI, THE CLI_Wrapper SHALL forward each key-value pair to the Runner subprocess.
6. WHEN the Runner subprocess exits with code 0, THE CLI_Wrapper SHALL return the parsed JSON result from stdout.
7. IF the Runner subprocess exits with a non-zero code, THEN THE CLI_Wrapper SHALL raise a RuntimeError with the stderr output.

### Requirement 9: Backward Compatibility

**User Story:** As a CI/CD pipeline operator, I want existing suite execution to continue working unchanged, so that current CI/CD integrations are not broken by the new features.

#### Acceptance Criteria

1. WHEN `--suite-id` is provided, THE Runner SHALL execute the full test suite using the existing `run_runner` function without any behavioral changes.
2. WHEN `--suite-id` is provided with `--token-file`, THE Runner SHALL authenticate using the token file and execute the suite normally.
3. WHEN `--suite-id` is provided without `--token-file`, THE Runner SHALL authenticate using client credentials from environment variables as before.
4. THE Runner SHALL preserve all existing CLI flags (`--base-url`, `--var`, `--region`, `--model-id`, `--verbose`, `--timeout`, `--keep-artifacts`) with identical behavior for suite execution.
5. THE Runner SHALL preserve exit code semantics: 0 for all tests passed, 1 for test failures, 2 for runner errors.
