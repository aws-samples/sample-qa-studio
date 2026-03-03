# Requirements Document

## Introduction

This feature adds EventBridge event emission to the worker after test execution completes. The emitted event triggers downstream cache building processes (Package 5: Cache Builder Lambda) that parse Nova Act responses and store cacheable steps in DynamoDB. This is a critical integration point in the step cache system that enables asynchronous cache building without blocking test execution.

## Glossary

- **Worker**: The Python process that executes test cases using Nova Act
- **EventBridge**: AWS service for event-driven architecture
- **Execution**: A single test run of a usecase with a unique execution_id
- **Usecase**: A test case definition with a unique usecase_id
- **Cache_Builder**: Downstream Lambda function that processes execution completion events
- **Execution_Status**: Final status of test execution (success or failed)

## Requirements

### Requirement 1: Event Emission After Execution

**User Story:** As a system architect, I want the Worker to emit an event after test execution completes, so that downstream processes can react to execution completion asynchronously.

#### Acceptance Criteria

1. WHEN an execution completes with status "success", THE Worker SHALL emit a usecase.execution.completed event to EventBridge
2. WHEN an execution completes with status "failed", THE Worker SHALL emit a usecase.execution.completed event to EventBridge
3. THE Worker SHALL emit the event after updating the execution status in DynamoDB
4. THE Worker SHALL emit the event before the worker process exits
5. IF event emission fails, THEN THE Worker SHALL log the error and continue (fire-and-forget pattern)

### Requirement 2: Event Structure and Content

**User Story:** As a Cache Builder developer, I want the event to contain all necessary execution metadata, so that I can identify and process the correct execution data.

#### Acceptance Criteria

1. THE Worker SHALL set the event source to "qa-studio.worker"
2. THE Worker SHALL set the event detail-type to "usecase.execution.completed"
3. THE Worker SHALL include usecase_id in the event detail
4. THE Worker SHALL include execution_id in the event detail
5. THE Worker SHALL include execution_status in the event detail (values: "success" or "failed")
6. THE Worker SHALL include timestamp in the event detail in ISO 8601 format with UTC timezone (YYYY-MM-DDTHH:MM:SS.ffffffZ)
7. THE Worker SHALL serialize the event detail as valid JSON

### Requirement 3: Non-Blocking Execution

**User Story:** As a QA engineer, I want event emission to not impact test execution time or reliability, so that adding this feature doesn't introduce new failure modes.

#### Acceptance Criteria

1. IF EventBridge client initialization fails, THEN THE Worker SHALL log the error and continue without emitting events
2. IF event emission fails, THEN THE Worker SHALL log the error and continue without retrying
3. THE Worker SHALL NOT wait for event delivery confirmation
4. THE Worker SHALL complete execution status updates before attempting event emission
5. THE Worker SHALL return the same success/failure status regardless of event emission outcome

### Requirement 4: AWS Permissions and Configuration

**User Story:** As a DevOps engineer, I want the Worker to use standard AWS SDK configuration, so that I can manage permissions through IAM roles.

#### Acceptance Criteria

1. THE Worker SHALL use boto3.client('events') to create the EventBridge client
2. THE Worker SHALL use the default AWS region from the boto3 session
3. THE Worker SHALL NOT require additional environment variables for EventBridge configuration
4. THE Worker SHALL rely on IAM role permissions for EventBridge access

### Requirement 5: Observability and Debugging

**User Story:** As a developer, I want clear logging around event emission, so that I can debug issues and verify the feature is working correctly.

#### Acceptance Criteria

1. WHEN an event is successfully emitted, THE Worker SHALL log the usecase_id, execution_id, and execution_status at INFO level
2. WHEN event emission fails, THE Worker SHALL log the error message and exception details at ERROR level
3. WHEN EventBridge client initialization fails, THE Worker SHALL log the error at ERROR level
4. THE Worker SHALL include the event detail JSON in debug logs (if debug logging is enabled)

### Requirement 6: Testing and Verification

**User Story:** As a developer, I want comprehensive unit tests for event emission, so that I can verify the feature works correctly without deploying to AWS.

#### Acceptance Criteria

1. THE test suite SHALL verify event emission for successful executions
2. THE test suite SHALL verify event emission for failed executions
3. THE test suite SHALL verify correct event structure (source, detail-type, detail fields)
4. THE test suite SHALL verify timestamp format is ISO 8601 with UTC timezone
5. THE test suite SHALL verify event emission does not block on errors
6. THE test suite SHALL verify worker continues on EventBridge client initialization failure
7. THE test suite SHALL use mocked boto3 clients to avoid AWS dependencies
8. THE test suite SHALL achieve at least 70% code coverage for event emission code
