# Requirements Document

## Introduction

This document specifies the requirements for Work Package 1 (WP1) of the Kiro IDE Extension project: CI/CD Runner Enhancement. The goal is to extend the existing CI/CD runner (`cicd-runner/`) to support single use case execution and a local-only execution mode. This enables the Kiro IDE extension to run individual test cases locally without creating execution records or uploading artifacts to S3, while preserving the existing suite execution functionality.

Reference: #[[file:.kiro/design/kiro-extension.md]]

## Glossary

- **Runner**: The CI/CD runner Python CLI application located at `cicd-runner/`, orchestrated via Click commands.
- **CLI**: The Click-based command-line interface defined in `cicd-runner/src/cli/parser.py`.
- **Use_Case**: A single test case definition in the QA Studio platform, identified by a UUID, containing metadata (name, starting_url, executing_region, model_id), steps, variables, and secrets.
- **Suite**: A collection of Use_Cases grouped for batch execution, identified by a UUID.
- **Execution_Record**: A server-side record created via `POST /usecase/{id}/execute` or `POST /test-suites/{id}/execute` that tracks execution status, step results, and artifacts.
- **Local_Only_Mode**: An execution mode where the Runner fetches the Use_Case definition, executes steps locally via Nova Act, stores artifacts on the local filesystem, and outputs JSON results to stdout — without creating Execution_Records or uploading artifacts to S3.
- **Normal_Usecase_Mode**: An execution mode where the Runner creates an Execution_Record via `POST /usecase/{id}/execute`, then follows the existing execution flow (fetch execution steps, execute, upload artifacts, update status).
- **UseCaseAPI**: A new API client class (`cicd-runner/src/api/usecases.py`) for fetching Use_Case definitions directly from the platform API.
- **ExecutionEngine**: The existing execution engine class (`cicd-runner/src/execution/engine.py`) responsible for running steps via Nova Act SDK.
- **Artifact_Directory**: The local directory `/tmp/qa-studio-artifacts/{usecase-id}/` where Local_Only_Mode stores execution artifacts.
- **OAuthClient**: The existing authentication module (`cicd-runner/src/auth/oauth_client.py`) that performs client_credentials grant against Cognito.
- **Settings**: The Pydantic configuration model (`cicd-runner/src/config/settings.py`) that loads runner configuration from environment variables.
- **APIClient**: The base HTTP client (`cicd-runner/src/api/client.py`) with Bearer token authentication used by all API classes.

## Requirements

### Requirement 1: Use Case ID CLI Flag

**User Story:** As a developer, I want to specify a single use case ID on the command line, so that I can execute an individual test case without needing a test suite.

#### Acceptance Criteria

1. THE CLI SHALL accept a `--usecase-id` option that takes a string value representing a Use_Case UUID.
2. WHEN both `--usecase-id` and `--suite-id` are provided, THE CLI SHALL reject the command with an error message stating that the two options are mutually exclusive.
3. WHEN neither `--usecase-id` nor `--suite-id` is provided, THE CLI SHALL reject the command with an error message stating that one of the two options is required.
4. WHEN `--usecase-id` is provided without `--suite-id`, THE Runner SHALL route execution to the use case execution path instead of the suite execution path.
5. THE CLI SHALL continue to accept all existing flags (`--base-url`, `--var`, `--region`, `--model-id`, `--verbose`, `--timeout`, `--keep-artifacts`) alongside `--usecase-id`.

### Requirement 2: Local-Only CLI Flag

**User Story:** As a developer using the Kiro IDE extension, I want a local-only execution mode, so that I can run tests without creating server-side execution records or uploading artifacts.

#### Acceptance Criteria

1. THE CLI SHALL accept a `--local-only` boolean flag that defaults to false.
2. WHEN `--local-only` is provided without `--usecase-id`, THE CLI SHALL reject the command with an error message stating that `--local-only` requires `--usecase-id`.
3. WHEN `--local-only` is provided with `--usecase-id`, THE Runner SHALL execute in Local_Only_Mode.
4. WHEN `--usecase-id` is provided without `--local-only`, THE Runner SHALL execute in Normal_Usecase_Mode.

### Requirement 3: UseCaseAPI Client

**User Story:** As a developer, I want the runner to fetch use case definitions directly from the platform API, so that local-only execution can retrieve test data without creating execution records.

#### Acceptance Criteria

1. THE UseCaseAPI SHALL provide a method to fetch Use_Case metadata (name, starting_url, executing_region, model_id) via `GET /usecase/{id}`.
2. THE UseCaseAPI SHALL provide a method to fetch Use_Case steps via `GET /usecase/{id}/steps`.
3. THE UseCaseAPI SHALL provide a method to fetch Use_Case variables via `GET /usecase/{id}/variables`.
4. THE UseCaseAPI SHALL provide a method to fetch Use_Case secret keys (with values resolved from Secrets Manager) via `GET /usecase/{id}/secrets`.
5. IF the platform API returns an error for any UseCaseAPI request, THEN THE UseCaseAPI SHALL raise an appropriate error with the HTTP status code and response body.
6. THE UseCaseAPI SHALL use the existing APIClient for all HTTP requests, inheriting Bearer token authentication.

### Requirement 4: Local-Only Execution Mode

**User Story:** As a developer using the Kiro IDE extension, I want the runner to execute a use case locally and return results as JSON, so that the extension can display test results without server-side side effects.

#### Acceptance Criteria

1. WHEN executing in Local_Only_Mode, THE Runner SHALL fetch the Use_Case definition using the UseCaseAPI (metadata, steps, variables, secrets).
2. WHEN executing in Local_Only_Mode, THE Runner SHALL skip creating any Execution_Records via the platform API.
3. WHEN executing in Local_Only_Mode, THE Runner SHALL skip uploading any artifacts to S3.
4. WHEN executing in Local_Only_Mode, THE Runner SHALL skip sending any status updates to the platform API.
5. WHEN executing in Local_Only_Mode, THE Runner SHALL store all artifacts (screenshots, video recording, logs) in the Artifact_Directory at `/tmp/qa-studio-artifacts/{usecase-id}/`.
6. WHEN executing in Local_Only_Mode, THE Runner SHALL execute all Use_Case steps using the Nova Act SDK via the ExecutionEngine.
7. WHEN Local_Only_Mode execution completes, THE Runner SHALL output a JSON result object to stdout.
8. THE JSON result object SHALL contain the following fields: `status` ("success" or "failed"), `usecaseId`, `usecaseName`, `duration` (in seconds), `steps` (array of step results), and `artifacts` (object with local file paths).
9. WHEN a step completes in Local_Only_Mode, THE step result SHALL contain: `stepId`, `instruction`, `status` ("success" or "failed"), `duration` (in seconds), and `screenshot` (local file path).
10. THE `artifacts` object in the JSON result SHALL contain `video` (path to recording.webm) and `logs` (path to execution.log) fields pointing to files in the Artifact_Directory.
11. IF a step fails during Local_Only_Mode execution, THEN THE Runner SHALL continue executing remaining steps and report the overall status as "failed".

### Requirement 5: Normal Single Use Case Execution Mode

**User Story:** As a CI/CD pipeline operator, I want to execute a single use case with full server-side tracking, so that execution history and artifacts are recorded in the platform.

#### Acceptance Criteria

1. WHEN executing in Normal_Usecase_Mode, THE Runner SHALL create an Execution_Record by calling `POST /usecase/{id}/execute` with query parameter `trigger-type=ci_runner`.
2. WHEN the Execution_Record is created, THE Runner SHALL follow the existing execution flow: fetch execution steps, execute via Nova Act, upload artifacts to S3, and update status via the platform API.
3. WHEN Normal_Usecase_Mode execution completes successfully, THE Runner SHALL exit with code 0.
4. WHEN Normal_Usecase_Mode execution fails, THE Runner SHALL exit with code 1.
5. IF the Runner encounters an internal error during Normal_Usecase_Mode, THEN THE Runner SHALL exit with code 2.

### Requirement 6: CLI Override Flags with Use Case Execution

**User Story:** As a developer, I want to override the base URL, variables, region, and model ID when executing a single use case, so that I can test against different environments and configurations.

#### Acceptance Criteria

1. WHEN `--base-url` is provided with `--usecase-id`, THE Runner SHALL override the Use_Case starting_url with the provided base URL value.
2. WHEN `--var` key=value pairs are provided with `--usecase-id`, THE Runner SHALL merge the provided variables with the Use_Case variables, with CLI-provided values taking precedence over Use_Case-defined values.
3. WHEN `--region` is provided with `--usecase-id`, THE Runner SHALL override the Use_Case executing_region with the provided region value.
4. WHEN `--model-id` is provided with `--usecase-id`, THE Runner SHALL override the Use_Case model_id with the provided model ID value.

### Requirement 7: Backward Compatibility

**User Story:** As a CI/CD pipeline operator, I want the existing suite execution functionality to remain unchanged, so that current pipelines continue to work without modification.

#### Acceptance Criteria

1. WHEN `--suite-id` is provided without `--usecase-id`, THE Runner SHALL execute the suite using the existing execution flow (OAuth → fetch suite → create suite execution → parallel use case execution → upload artifacts → update status → summary → exit code).
2. THE existing `run_runner()` function signature and behavior SHALL remain unchanged for suite execution.
3. THE existing exit code semantics SHALL remain unchanged: 0 for all tests passed, 1 for one or more tests failed, 2 for runner error.
4. THE existing CLI flags (`--base-url`, `--var`, `--region`, `--model-id`, `--verbose`, `--timeout`, `--keep-artifacts`) SHALL continue to function identically for suite execution.

### Requirement 8: Local-Only Exit Code and Output Semantics

**User Story:** As a developer integrating the runner with the Kiro IDE extension, I want predictable exit codes and clean stdout output, so that the extension can reliably parse results.

#### Acceptance Criteria

1. WHEN Local_Only_Mode execution completes with all steps passing, THE Runner SHALL exit with code 0.
2. WHEN Local_Only_Mode execution completes with one or more steps failing, THE Runner SHALL exit with code 1.
3. IF the Runner encounters an internal error during Local_Only_Mode execution, THEN THE Runner SHALL exit with code 2.
4. WHEN executing in Local_Only_Mode, THE Runner SHALL write only the JSON result object to stdout and direct all log output to stderr.
5. THE JSON result object written to stdout SHALL be valid, parseable JSON.

### Requirement 9: Artifact Directory Management

**User Story:** As a developer, I want local artifacts to be stored in a predictable location, so that the Kiro IDE extension can locate and display them.

#### Acceptance Criteria

1. WHEN executing in Local_Only_Mode, THE Runner SHALL create the Artifact_Directory at `/tmp/qa-studio-artifacts/{usecase-id}/` if the directory does not exist.
2. WHEN executing in Local_Only_Mode, THE Runner SHALL store step screenshots as `step-{step-number}-screenshot.png` in the Artifact_Directory.
3. WHEN executing in Local_Only_Mode, THE Runner SHALL store the video recording as `recording.webm` in the Artifact_Directory.
4. WHEN executing in Local_Only_Mode, THE Runner SHALL store the execution log as `execution.log` in the Artifact_Directory.
5. IF the Artifact_Directory already exists from a previous execution, THEN THE Runner SHALL clear the directory contents before starting a new execution.
