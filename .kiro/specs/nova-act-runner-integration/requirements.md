# Requirements Document

## Introduction

The CI/CD runner's execution engine (`qa-studio-ci-runner/src/execution/engine.py`) currently references a fictional `nova_act_sdk` module that does not exist. The real Nova Act integration is already implemented in the `worker/` directory using `nova_act.NovaAct`, `nova_act.Workflow`, and `bedrock_agentcore.tools.browser_client.BrowserClient` for remote browser management. This feature replaces the fictional SDK integration with the real Nova Act SDK, adapting the worker's proven patterns for the CI/CD runner context. The runner communicates with the platform via HTTP API (not DynamoDB), runs locally with AWS credentials, and must handle the full browser lifecycle (create → start → use → stop → delete) plus all step types (navigation, validation, retrieve_value, url, assertion, secret, download).

## Glossary

- **Execution_Engine**: The Python class in `qa-studio-ci-runner/src/execution/engine.py` responsible for orchestrating test execution using Nova Act.
- **Nova_Act**: The real Nova Act SDK (`nova_act.NovaAct`) used as a synchronous context manager to control a remote browser via CDP.
- **Workflow**: The `nova_act.Workflow` class used for Nova Act GA Service mode, wrapping NovaAct sessions with workflow definitions.
- **Browser_Manager**: The component responsible for creating, starting, polling, stopping, and deleting remote browsers via the `bedrock-agentcore-control` boto3 client and `BrowserClient`.
- **Step_Executor**: The component responsible for dispatching and executing individual test steps by type (navigation, validation, retrieve_value, url, assertion, secret, download).
- **Execution_API**: The existing HTTP API client (`qa-studio-ci-runner/src/api/executions.py`) used to communicate execution and step status to the platform backend.
- **Artifact_Uploader**: The existing component that uploads execution artifacts (logs, recordings) to S3 via presigned URLs.
- **Variable_Resolver**: The component responsible for replacing `{{variable}}` placeholders in step instructions and managing runtime variables captured during execution.
- **Step_Status_Reporter**: The component responsible for reporting individual step execution status (success/error, logs, actual values) back to the platform API.

## Requirements

### Requirement 1: Replace Fictional SDK with Real Nova Act Imports

**User Story:** As a CI/CD runner developer, I want the engine to use the real Nova Act SDK imports, so that the runner can actually execute browser-based tests.

#### Acceptance Criteria

1. THE Execution_Engine SHALL import `NovaAct` from the `nova_act` package.
2. THE Execution_Engine SHALL import `Workflow` from the `nova_act` package for GA Service mode.
3. THE Execution_Engine SHALL NOT import from `nova_act_sdk` or any other fictional module.
4. THE Execution_Engine SHALL import `BrowserClient` from `bedrock_agentcore.tools.browser_client` for browser session management.

### Requirement 2: Browser Lifecycle Management

**User Story:** As a CI/CD runner, I want to manage remote browser sessions through the full lifecycle, so that Nova Act has a browser to control during test execution.

#### Acceptance Criteria

1. WHEN an execution starts, THE Browser_Manager SHALL create a browser via the `bedrock-agentcore-control` boto3 client with a unique name, the execution role ARN from the `BEDROCK_EXECUTION_ROLE` environment variable, and recording configuration.
2. WHEN a browser is created, THE Browser_Manager SHALL poll the browser status until it reaches the READY state, with a maximum wait time of 600 seconds and 1-second polling intervals.
3. IF the browser status reaches FAILED or DELETED during polling, THEN THE Browser_Manager SHALL raise an error with the failure status.
4. IF the browser does not reach READY within the maximum wait time, THEN THE Browser_Manager SHALL raise a timeout error.
5. WHEN the browser is READY, THE Browser_Manager SHALL start a browser session using `BrowserClient` and obtain the WebSocket URL and CDP headers.
6. WHEN the execution completes (regardless of success or failure), THE Browser_Manager SHALL stop the browser session and delete the browser resource.
7. THE Browser_Manager SHALL support both PUBLIC and VPC network modes based on environment configuration.
8. THE Browser_Manager SHALL configure S3 recording when a `NOVA_ACT_S3_BUCKET` environment variable is provided.

### Requirement 3: Nova Act Session Management

**User Story:** As a CI/CD runner, I want to establish Nova Act sessions using the real SDK context manager pattern, so that I can execute browser actions reliably.

#### Acceptance Criteria

1. THE Execution_Engine SHALL use `NovaAct` as a synchronous context manager with the CDP WebSocket URL, CDP headers, starting page URL, and `headless=True`.
2. WHEN the `USE_NOVA_ACT_GA` environment variable is set to `true`, THE Execution_Engine SHALL create a `Workflow` instance and pass it to the `NovaAct` context manager.
3. WHEN the `USE_NOVA_ACT_GA` environment variable is not set or set to `false`, THE Execution_Engine SHALL use the Nova Act Preview API mode with an API key from the `NOVA_ACT_API_KEY` environment variable.
4. THE Execution_Engine SHALL execute all Nova Act operations synchronously (not using async/await for Nova Act calls), since the Nova Act SDK is synchronous.
5. WHEN a `Workflow` is used, THE Execution_Engine SHALL ensure the workflow definition exists (creating it if needed) before starting the Nova Act session.

### Requirement 4: Step Type Dispatching

**User Story:** As a CI/CD runner, I want to execute all supported step types correctly, so that the full range of test scenarios can run in CI/CD pipelines.

#### Acceptance Criteria

1. WHEN a step has type `navigation`, THE Step_Executor SHALL call `nova.act(instruction)` and return the result.
2. WHEN a step has type `validation`, THE Step_Executor SHALL call `nova.act_get(instruction, schema=SCHEMA)` with the appropriate schema based on the validation type (string, number, bool), and compare the result against the expected value using the specified operator (exact, contains, not_equal, greater_then, less_then, equals, and their case-insensitive and boundary variants).
3. WHEN a step has type `retrieve_value`, THE Step_Executor SHALL call `nova.act_get(instruction, schema=SCHEMA)` with the appropriate schema and return the retrieved value for runtime variable capture.
4. WHEN a step has type `url`, THE Step_Executor SHALL call `nova.go_to_url(instruction)` to navigate directly to the specified URL.
5. WHEN a step has type `assertion`, THE Step_Executor SHALL compare a runtime variable against an expected value using the specified operator without making any Nova Act calls.
6. WHEN a step has type `secret`, THE Step_Executor SHALL resolve the secret value, execute the instruction via `nova.act()`, and type the secret value using `nova.page.keyboard.type()`.
7. WHEN a step has type `download`, THE Step_Executor SHALL trigger the download action via `nova.act()`, capture the downloaded file, and upload it to S3.
8. IF a step type is not recognized, THE Step_Executor SHALL treat the step as a navigation step and execute it with `nova.act(instruction)`.

### Requirement 5: Step Status Reporting via API

**User Story:** As a platform user, I want to see individual step results in the UI during CI/CD runs, so that I can identify exactly which step failed.

#### Acceptance Criteria

1. WHEN a step completes successfully, THE Step_Status_Reporter SHALL send a status update to the platform API with status `completed`, the act_id from the Nova Act result metadata, and any logs.
2. WHEN a step fails, THE Step_Status_Reporter SHALL send a status update to the platform API with status `failed`, the error message in the logs field, and the actual value if applicable.
3. WHEN a validation or retrieve_value step completes, THE Step_Status_Reporter SHALL include the actual value in the status update.
4. IF the step status API call fails, THEN THE Step_Status_Reporter SHALL log the error and continue execution without failing the overall test.
5. THE Execution_API SHALL provide a method to update individual step status via the `PATCH /usecase/{usecase_id}/executions/{execution_id}/steps/{step_id}/status` endpoint.

### Requirement 6: Variable Resolution and Runtime Variables

**User Story:** As a test author, I want variables to be resolved in step instructions and runtime variables to be captured during execution, so that dynamic test data flows correctly.

#### Acceptance Criteria

1. THE Variable_Resolver SHALL replace all `{{variable_name}}` placeholders in step instructions with values from the execution variables before executing each step.
2. WHEN a `retrieve_value` step completes successfully and has a `capture_variable` field, THE Variable_Resolver SHALL store the retrieved value as a runtime variable for use in subsequent steps.
3. WHEN an `assertion` step references a runtime variable, THE Variable_Resolver SHALL provide the current runtime variable values for comparison.
4. IF a variable placeholder references a variable that does not exist, THEN THE Variable_Resolver SHALL log a warning and leave the placeholder unchanged.

### Requirement 7: Synchronous Execution within Async Orchestration

**User Story:** As a CI/CD runner developer, I want the Nova Act execution to run synchronously within the async orchestration layer, so that the synchronous Nova Act SDK works correctly while parallel execution of multiple usecases is preserved.

#### Acceptance Criteria

1. THE Execution_Engine SHALL run each usecase's Nova Act execution in a separate thread using `asyncio.to_thread()` or equivalent, since Nova Act is synchronous and the orchestration layer uses asyncio for parallel usecase execution.
2. WHEN multiple usecases are executed in parallel, THE Execution_Engine SHALL ensure each usecase gets its own browser instance and Nova Act session, with no shared state between them.
3. THE Execution_Engine SHALL preserve the existing `execute_all()` async interface that uses `asyncio.gather()` for parallel usecase execution.

### Requirement 8: Dependencies and Configuration

**User Story:** As a CI/CD runner operator, I want the correct dependencies and environment variables documented and validated, so that the runner can be configured correctly.

#### Acceptance Criteria

1. THE `qa-studio-ci-runner/requirements.txt` SHALL include `nova-act==3.1.157.0` and `bedrock_agentcore==1.0.5` as dependencies.
2. THE Execution_Engine SHALL require the `BEDROCK_EXECUTION_ROLE` environment variable and raise a clear error if it is missing.
3. WHEN the GA Service mode is enabled, THE Execution_Engine SHALL require the `NOVA_ACT_S3_BUCKET` environment variable and raise a clear error if it is missing.
4. WHEN the Preview API mode is used, THE Execution_Engine SHALL require the `NOVA_ACT_API_KEY` environment variable and raise a clear error if it is missing.

### Requirement 9: Error Handling and Cleanup

**User Story:** As a CI/CD runner operator, I want robust error handling and resource cleanup, so that browser resources are not leaked and failures are reported clearly.

#### Acceptance Criteria

1. IF Nova Act raises an exception during step execution, THEN THE Execution_Engine SHALL catch the exception, record the step as failed with the error message, and stop executing further steps for that usecase.
2. IF browser creation or startup fails, THEN THE Execution_Engine SHALL report the failure and attempt to clean up any partially created browser resources.
3. WHEN an execution completes (whether successfully or with failure), THE Execution_Engine SHALL always stop the browser session and delete the browser resource in a finally block.
4. THE Execution_Engine SHALL sanitize all error messages before sending them to the API to prevent leaking sensitive information (URLs with tokens, credentials).
5. IF the Nova Act context manager raises an exception, THEN THE Execution_Engine SHALL ensure the browser cleanup still occurs.

### Requirement 10: Execution Artifact Handling

**User Story:** As a CI/CD runner operator, I want execution logs and recordings to be captured and uploaded, so that I can debug test failures.

#### Acceptance Criteria

1. THE Execution_Engine SHALL configure a logs directory for each execution and pass it to the Nova Act context manager.
2. WHEN a `NOVA_ACT_S3_BUCKET` is configured, THE Execution_Engine SHALL configure S3-based recording via the browser creation API.
3. WHEN an execution completes, THE Artifact_Uploader SHALL upload execution-level artifacts (logs) via the existing presigned URL mechanism.
4. THE Execution_Engine SHALL clean up temporary local artifact files after upload.
