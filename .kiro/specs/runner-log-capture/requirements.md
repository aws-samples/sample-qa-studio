# Requirements Document

## Introduction

The CI/CD runner currently captures per-usecase logs via `ArtifactCapture.setup_logs()` and uploads them as execution-level artifacts. However, two gaps exist:

1. **No suite-level log capture**: There is no mechanism to capture all logs across the entire suite run (authentication, suite setup, parallel orchestration, summary generation) and upload them as a suite execution artifact.
2. **Usecase log isolation is missing**: Each usecase's `setup_logs()` attaches a `FileHandler` to the root logger without scoping, so logs from parallel usecases bleed into each other's log files.

This feature adds suite-level log capture with upload to suite execution artifacts, and ensures per-usecase logs are properly isolated so each usecase artifact contains only its own logs.

## Glossary

- **Runner**: The CI/CD runner application (`qa-studio-ci-runner/`) that executes test suites
- **Suite_Log_Capture**: The module responsible for capturing all logs during a complete suite execution run
- **Usecase_Log_Capture**: The per-usecase log capture within `ArtifactCapture` that writes logs for a single usecase execution
- **Suite_Execution**: A single run of a test suite, identified by `suite_execution_id`, containing one or more usecase executions
- **Execution_API**: The API client module used by the runner to communicate with the platform backend
- **Artifact_Uploader**: The module that uploads artifact files to S3 via presigned URLs
- **Suite_Artifact_Endpoint**: A new API endpoint for uploading artifacts at the suite execution level
- **Log_Filter**: A Python logging filter that restricts which log records a handler processes
- **Frontend**: The React-based web application using Cloudscape Design System components
- **Suite_Artifact_List_Endpoint**: A new API endpoint for listing artifacts and generating presigned download URLs at the suite execution level

## Requirements

### Requirement 1: Capture suite-level logs for the entire runner execution

**User Story:** As a CI/CD operator, I want all logs from the entire suite run captured into a single log file, so that I can debug issues across the full execution lifecycle including authentication, setup, and orchestration.

#### Acceptance Criteria

1. WHEN the Runner starts a suite execution, THE Suite_Log_Capture SHALL create a log file at `~/.ci_runner/{suite_execution_id}/suite_logs.txt` and attach a file handler to the root logger
2. THE Suite_Log_Capture SHALL capture all log records from all loggers (including third-party libraries) for the duration of the suite execution
3. WHEN a log record is written to the suite log file, THE Suite_Log_Capture SHALL format each line as `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
4. WHEN the suite execution completes (regardless of success or failure), THE Suite_Log_Capture SHALL flush and close the file handler before upload
5. IF the suite log directory cannot be created, THEN THE Runner SHALL log a warning and continue execution without suite-level log capture

### Requirement 2: Upload suite-level logs as a suite execution artifact

**User Story:** As a CI/CD operator, I want the suite log file uploaded to the platform, so that I can view it alongside the suite execution results in the UI.

#### Acceptance Criteria

1. WHEN the suite execution completes and the suite log file exists, THE Artifact_Uploader SHALL upload the suite log file as a suite execution artifact with type `logs`
2. WHEN uploading a suite execution artifact, THE Artifact_Uploader SHALL request a presigned URL from the Suite_Artifact_Endpoint at `POST /test-suites/{suite_id}/executions/{suite_execution_id}/artifacts`
3. WHEN the presigned URL is obtained, THE Artifact_Uploader SHALL upload the file to S3 using a PUT request with content type `text/plain`
4. IF the suite log upload fails after 3 retry attempts, THEN THE Runner SHALL log an error and continue with the normal exit code based on test results
5. THE Suite_Artifact_Endpoint SHALL require the `api/suites.write` OAuth scope

### Requirement 3: Isolate per-usecase logs during parallel execution

**User Story:** As a CI/CD operator, I want each usecase's log file to contain only logs from that specific usecase execution, so that I can debug individual usecase failures without noise from other parallel executions.

#### Acceptance Criteria

1. WHEN the Usecase_Log_Capture sets up logging for a usecase execution, THE Usecase_Log_Capture SHALL attach a Log_Filter to the file handler that only accepts log records originating from that usecase's execution thread
2. WHILE multiple usecases execute in parallel, THE Usecase_Log_Capture SHALL ensure each usecase's log file contains only log records from its own execution thread
3. THE Suite_Log_Capture SHALL continue to capture all log records from all threads without filtering
4. WHEN the usecase execution completes, THE Usecase_Log_Capture SHALL remove the file handler and Log_Filter from the root logger

### Requirement 4: Suite artifact upload API endpoint

**User Story:** As a CI/CD operator, I want a backend endpoint that generates presigned URLs for suite-level artifacts, so that the runner can upload suite logs to S3.

#### Acceptance Criteria

1. THE Suite_Artifact_Endpoint SHALL accept POST requests at `/test-suites/{suite_id}/executions/{suite_execution_id}/artifacts` with a JSON body containing `type`, `filename`, and `content_type` fields
2. WHEN a valid request is received, THE Suite_Artifact_Endpoint SHALL generate a presigned S3 URL for uploading the artifact to the path `suites/{suite_id}/{suite_execution_id}/{filename}`
3. WHEN a valid request is received, THE Suite_Artifact_Endpoint SHALL return a JSON response containing `upload_url`, `expires_in`, and `s3_key`
4. THE Suite_Artifact_Endpoint SHALL validate that the requesting client has the `api/suites.write` OAuth scope
5. THE Suite_Artifact_Endpoint SHALL have the Cognito authorizer attached
6. IF the suite execution does not exist, THEN THE Suite_Artifact_Endpoint SHALL return a 404 response

### Requirement 5: Filter nova-act logs from CLI output

**User Story:** As a CI/CD operator, I want nova-act library logs suppressed from the CLI output, so that the console remains readable and focused on runner progress without verbose browser automation noise.

#### Acceptance Criteria

1. THE Runner SHALL attach a Log_Filter to the console handler that rejects log records originating from the `nova_act` logger hierarchy
2. WHILE the console handler filters nova-act log records, THE Suite_Log_Capture SHALL continue to capture nova-act log records in the suite log file
3. WHILE the console handler filters nova-act log records, THE Usecase_Log_Capture SHALL continue to capture nova-act log records in the per-usecase log file
4. WHEN the Runner initializes logging via `setup_logging`, THE Runner SHALL apply the nova-act filter only to the console `StreamHandler`, not to any file handlers


### Requirement 6: Display log content in the frontend UI

**User Story:** As a platform user, I want to view suite-level and usecase-level log content directly in the UI rendered in a code block, so that I can inspect runner logs without downloading files manually.

#### Acceptance Criteria

1. WHEN a user navigates to a suite execution detail page, THE Frontend SHALL fetch the list of artifacts for that suite execution from `GET /test-suites/{suite_id}/executions/{suite_execution_id}/artifacts`
2. WHEN a log artifact is available, THE Frontend SHALL fetch the log file content using the presigned download URL returned by the artifact list endpoint
3. WHEN log content is fetched successfully, THE Frontend SHALL render the log text inside a Cloudscape `CodeView` component with syntax highlighting disabled and line numbers enabled
4. WHILE log content is being fetched, THE Frontend SHALL display a loading indicator within the log container
5. IF the log content fetch fails, THEN THE Frontend SHALL display an error alert with a retry option inside the log container
6. THE Suite_Artifact_List_Endpoint SHALL accept GET requests at `/test-suites/{suite_id}/executions/{suite_execution_id}/artifacts`, use S3 ListObjectsV2 with prefix `suites/{suite_id}/{suite_execution_id}/` to discover artifacts, and return a JSON array including `filename`, `type`, `content_type`, and `download_url` for each object found
7. THE Suite_Artifact_List_Endpoint SHALL require the `api/suites.read` OAuth scope and have the Cognito authorizer attached
8. WHEN a user views a usecase execution that has a log artifact, THE Frontend SHALL render the usecase log content using the same `CodeView` component pattern used for suite-level logs
