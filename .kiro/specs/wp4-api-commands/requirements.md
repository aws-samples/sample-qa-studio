# Requirements Document

## Introduction

WP4 adds API wrapper commands to the QA Studio CLI, enabling test (usecase) and suite management directly from the terminal. The CLI already has authentication (WP1), local runner integration (WP2), and agent skills (WP3). This work package builds an API client module and two command groups (`tests` and `suites`) that call the existing backend REST API with proper OAuth token handling and camelCase ↔ snake_case conversion.

## Glossary

- **CLI**: The `qa-studio` Click-based command-line interface installed via `qa-studio-cli/setup.py`.
- **API_Client**: A Python module (`qa_studio_cli/api/client.py`) responsible for making authenticated HTTP requests to the QA Studio backend API.
- **Token_Manager**: The existing module (`qa_studio_cli/auth/token_manager.py`) that loads, validates, and refreshes OAuth access tokens.
- **Config_Loader**: The existing module (`qa_studio_cli/utils/config.py`) that loads the CLI configuration including `api_url`.
- **Test**: A use case (usecase) record in the QA Studio backend, identified by a UUID.
- **Suite**: A test suite record in the QA Studio backend, identified by a UUID, containing references to one or more Tests.
- **Usecase_Model**: A Pydantic model representing a test/usecase as returned by the API.
- **Suite_Model**: A Pydantic model representing a test suite as returned by the API.
- **API_Error**: A custom exception raised when the backend API returns a non-success HTTP status code.
- **OAuth_Scope**: A Cognito scope string (e.g. `api/usecases.read`) that authorizes access to specific API endpoints.

## Requirements

### Requirement 1: API Client — Authenticated Requests

**User Story:** As a CLI user, I want the CLI to make authenticated HTTP requests to the QA Studio API, so that I can manage tests and suites from the terminal.

#### Acceptance Criteria

1. THE API_Client SHALL load the base URL from Config_Loader and the access token from Token_Manager for every request.
2. THE API_Client SHALL set the `Authorization: Bearer <token>` header and `Content-Type: application/json` header on every outgoing request.
3. WHEN Token_Manager returns a valid access token, THE API_Client SHALL use that token without prompting the user.
4. IF Token_Manager raises an AuthError, THEN THE API_Client SHALL propagate the error with a message instructing the user to run `qa-studio login`.
5. THE API_Client SHALL provide methods for GET, POST, and DELETE HTTP verbs, each accepting a path and optional JSON body or query parameters.
6. WHEN the API returns a response with status code 2xx, THE API_Client SHALL return the parsed JSON response body.
7. IF the API returns a 401 status code, THEN THE API_Client SHALL raise an API_Error with a message indicating the session has expired and the user should run `qa-studio login`.
8. IF the API returns a 403 status code, THEN THE API_Client SHALL raise an API_Error with a message indicating insufficient permissions.
9. IF the API returns a 404 status code, THEN THE API_Client SHALL raise an API_Error with a message indicating the resource was not found.
10. IF the API returns any other non-2xx status code, THEN THE API_Client SHALL raise an API_Error containing the HTTP status code and the error message from the response body.

### Requirement 2: API Response Model Conversion

**User Story:** As a developer, I want API responses to be converted from camelCase JSON into snake_case Pydantic models, so that the CLI code uses idiomatic Python naming.

#### Acceptance Criteria

1. THE API_Client SHALL convert camelCase keys in API JSON responses to snake_case before returning data to callers.
2. THE Usecase_Model SHALL be a Pydantic model with fields: `id`, `name`, `description`, `starting_url`, `active`, `tags`, `created_at`, `executing_region`, `model_id`.
3. THE Suite_Model SHALL be a Pydantic model with fields: `id`, `name`, `description`, `tags`, `created_at`, `created_by`, `total_usecases`.
4. THE API_Client SHALL validate API responses against the corresponding Pydantic model and raise an API_Error when validation fails.

### Requirement 3: Tests List Command

**User Story:** As a CLI user, I want to list all tests, so that I can see which tests exist in QA Studio.

#### Acceptance Criteria

1. WHEN the user runs `qa-studio tests list`, THE CLI SHALL send a GET request to `/api/usecases` with OAuth_Scope `api/usecases.read`.
2. WHEN the API returns a list of tests, THE CLI SHALL display each test's name and ID in a tabular format.
3. WHEN the API returns an empty list, THE CLI SHALL display a message indicating no tests were found.
4. IF the API request fails, THEN THE CLI SHALL display the error message from API_Error and exit with a non-zero status code.

### Requirement 4: Tests Get Command

**User Story:** As a CLI user, I want to view details of a specific test, so that I can inspect its configuration.

#### Acceptance Criteria

1. WHEN the user runs `qa-studio tests get <id>`, THE CLI SHALL send a GET request to `/api/usecases/<id>` with OAuth_Scope `api/usecases.read`.
2. WHEN the API returns the test, THE CLI SHALL display the test's name, description, starting URL, active status, region, model, tags, and creation date.
3. IF the API returns 404, THEN THE CLI SHALL display a message indicating the test was not found and exit with a non-zero status code.

### Requirement 5: Tests Create from Journey Command

**User Story:** As a CLI user, I want to generate a test from a user journey description, so that I can quickly create tests using AI.

#### Acceptance Criteria

1. WHEN the user runs `qa-studio tests create --from-journey`, THE CLI SHALL prompt for title, starting URL, user journey description, and region.
2. THE CLI SHALL send a POST request to `/api/usecases/generate` with OAuth_Scope `api/usecases.write` containing the collected inputs.
3. WHEN the API returns generated usecase data, THE CLI SHALL send a POST request to `/api/usecases/import` with OAuth_Scope `api/usecases.write` to create the test.
4. WHEN the import succeeds, THE CLI SHALL display the created test's ID and name.
5. IF the generation fails, THEN THE CLI SHALL display the error message and exit with a non-zero status code.

### Requirement 6: Tests Delete Command

**User Story:** As a CLI user, I want to delete a test, so that I can remove tests that are no longer needed.

#### Acceptance Criteria

1. WHEN the user runs `qa-studio tests delete <id>`, THE CLI SHALL prompt for confirmation before proceeding.
2. WHEN the user confirms, THE CLI SHALL send a DELETE request to `/api/usecases/<id>` with OAuth_Scope `api/usecases.write`.
3. WHEN the deletion succeeds, THE CLI SHALL display a confirmation message.
4. WHEN the user passes `--yes` flag, THE CLI SHALL skip the confirmation prompt.
5. IF the API returns 404, THEN THE CLI SHALL display a message indicating the test was not found.

### Requirement 7: Suites List Command

**User Story:** As a CLI user, I want to list all test suites, so that I can see which suites exist.

#### Acceptance Criteria

1. WHEN the user runs `qa-studio suites list`, THE CLI SHALL send a GET request to `/api/test-suites` with OAuth_Scope `api/suite.read`.
2. WHEN the API returns a list of suites, THE CLI SHALL display each suite's name, ID, and total usecase count in a tabular format.
3. WHEN the API returns an empty list, THE CLI SHALL display a message indicating no suites were found.

### Requirement 8: Suites Get Command

**User Story:** As a CLI user, I want to view details of a specific suite, so that I can inspect its configuration and contents.

#### Acceptance Criteria

1. WHEN the user runs `qa-studio suites get <id>`, THE CLI SHALL send a GET request to `/api/test-suites/<id>` with OAuth_Scope `api/suite.read`.
2. WHEN the API returns the suite, THE CLI SHALL display the suite's name, description, tags, total usecases, created by, and creation date.
3. IF the API returns 404, THEN THE CLI SHALL display a message indicating the suite was not found and exit with a non-zero status code.

### Requirement 9: Suites Create Command

**User Story:** As a CLI user, I want to create a new test suite, so that I can group tests for batch execution.

#### Acceptance Criteria

1. WHEN the user runs `qa-studio suites create`, THE CLI SHALL accept `--name` and `--description` as required options and `--tags` as an optional repeatable option.
2. THE CLI SHALL send a POST request to `/api/test-suites` with OAuth_Scope `api/suite.write` containing the name, description, and tags.
3. WHEN the creation succeeds, THE CLI SHALL display the created suite's ID and name.
4. IF the name is missing or empty, THEN THE CLI SHALL display a validation error and exit with a non-zero status code without calling the API.

### Requirement 10: Suites Add-Tests Command

**User Story:** As a CLI user, I want to add tests to a suite, so that I can compose suites from existing tests.

#### Acceptance Criteria

1. WHEN the user runs `qa-studio suites add-tests <suite-id> <usecase-ids...>`, THE CLI SHALL send a POST request to `/api/test-suites/<suite-id>/usecases` with OAuth_Scope `api/suite.write` containing the list of usecase IDs.
2. WHEN the API returns a success response, THE CLI SHALL display the number of tests added and the new total.
3. IF the suite is not found, THEN THE CLI SHALL display a message indicating the suite was not found and exit with a non-zero status code.

### Requirement 11: Suites Remove-Test Command

**User Story:** As a CLI user, I want to remove a test from a suite, so that I can adjust suite composition.

#### Acceptance Criteria

1. WHEN the user runs `qa-studio suites remove-test <suite-id> <usecase-id>`, THE CLI SHALL send a DELETE request to `/api/test-suites/<suite-id>/usecases/<usecase-id>` with OAuth_Scope `api/suite.write`.
2. WHEN the API returns 204, THE CLI SHALL display a confirmation message.
3. IF the suite or test mapping is not found, THEN THE CLI SHALL display a message indicating the resource was not found.

### Requirement 12: Suites Run Command

**User Story:** As a CLI user, I want to execute a test suite via the API, so that I can trigger CI/CD suite runs from the terminal.

#### Acceptance Criteria

1. WHEN the user runs `qa-studio suites run <suite-id>`, THE CLI SHALL send a POST request to `/api/test-suites/<suite-id>/execute` with OAuth_Scope `api/suite.write` and `api/executions.write`, with `trigger_type` set to `ci_runner`.
2. THE CLI SHALL accept optional `--base-url`, `--var KEY=VALUE` (repeatable), `--region`, and `--model-id` flags to pass as execution overrides.
3. WHEN the API returns a success response, THE CLI SHALL display the suite execution ID and the number of usecase executions created.
4. IF the suite has no usecases, THEN THE CLI SHALL display the error message from the API and exit with a non-zero status code.
5. IF variable validation fails, THEN THE CLI SHALL display the unresolved variables error from the API and exit with a non-zero status code.

### Requirement 13: API Error Model

**User Story:** As a developer, I want a dedicated API error type, so that API failures are handled consistently across all commands.

#### Acceptance Criteria

1. THE API_Error SHALL be a Python exception with attributes: `status_code` (int), `message` (str), and `error_code` (optional str).
2. THE API_Error SHALL provide a human-readable string representation including the status code and message.
3. WHEN any command catches an API_Error, THE CLI SHALL display the error message to stderr and exit with status code 1.

### Requirement 14: Require-Auth Decorator

**User Story:** As a developer, I want a reusable decorator that ensures the user is authenticated before executing any API command, so that authentication checks are not duplicated.

#### Acceptance Criteria

1. THE CLI SHALL provide a `require_auth` decorator that loads the config and obtains a valid token before the wrapped command executes.
2. IF the config is missing, THEN THE decorator SHALL display a message to run `qa-studio configure` and exit with a non-zero status code.
3. IF the token is missing or expired and cannot be refreshed, THEN THE decorator SHALL display a message to run `qa-studio login` and exit with a non-zero status code.
4. WHEN authentication succeeds, THE decorator SHALL pass the API_Client instance to the wrapped command via Click's context.

### Requirement 15: Unit Test Coverage

**User Story:** As a developer, I want comprehensive unit tests for the API client and all commands, so that regressions are caught early.

#### Acceptance Criteria

1. THE test suite SHALL achieve a minimum of 70% line coverage across the `api/` and `commands/` modules.
2. THE test suite SHALL mock all HTTP requests using `unittest.mock` or `responses` library, making no real network calls.
3. THE test suite SHALL include tests for success paths, error paths (401, 403, 404, 500), and edge cases (empty lists, missing fields) for every command.
4. THE test suite SHALL include tests verifying camelCase-to-snake_case conversion of API responses.
