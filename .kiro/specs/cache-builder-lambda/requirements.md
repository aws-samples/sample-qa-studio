# Requirements Document

## Introduction

The Cache Builder Lambda is an event-driven system that automatically builds step caches from Nova Act responses after successful test executions. When a test execution completes successfully and caching is enabled, this Lambda processes the Nova Act response files stored in S3, extracts cacheable actions (click, hover, scroll, type, navigate), and updates the corresponding STEP records in DynamoDB with the parsed cache data. This enables subsequent test executions to replay cached steps directly via Playwright API instead of calling Nova Act, reducing execution time by 40-60%.

## Glossary

- **Cache_Builder_Lambda**: AWS Lambda function that processes Nova Act responses and builds step caches
- **Nova_Act**: AWS Bedrock service that generates browser automation actions from natural language instructions
- **STEP**: DynamoDB record representing a test step template in a usecase (pk: USECASE#{usecase_id}, sk: STEP#{step_id})
- **EXECUTION_STEP**: DynamoDB record representing a test step instance during execution (pk: EXECUTION#{execution_id}, sk: EXECUTION_STEP#{step_id})
- **Cache_Parser**: Module (worker/cache_parser.py) that parses Nova Act rawProgramBody into structured cacheable actions
- **EventBridge**: AWS service that routes events between services
- **S3_Act_File**: JSON file containing Nova Act response stored at s3://{bucket}/executions/{execution_id}/act_{act_id}.json
- **Cacheable_Action**: Browser action that can be replayed (click, hover, scroll, type, navigate)
- **DynamoDB_Table**: Single-table design database storing all QA Studio records
- **Worker**: ECS Fargate task that executes test steps and emits completion events

## Requirements

### Requirement 1: Event-Driven Activation

**User Story:** As a QA engineer, I want the cache builder to automatically process successful test executions, so that I don't need to manually trigger cache building.

#### Acceptance Criteria

1. WHEN a `usecase.execution.completed` event is received from EventBridge, THE Cache_Builder_Lambda SHALL process the event
2. THE Cache_Builder_Lambda SHALL be triggered by an EventBridge rule matching source `qa-studio.worker` and detail-type `usecase.execution.completed`
3. THE Cache_Builder_Lambda SHALL extract `usecase_id`, `execution_id`, `execution_status`, and `timestamp` from the event detail
4. IF `execution_status` is not `success`, THEN THE Cache_Builder_Lambda SHALL log the skip reason and return without processing
5. THE Cache_Builder_Lambda SHALL use fire-and-forget error handling where failures are logged but do not raise exceptions

### Requirement 2: Cache Eligibility Verification

**User Story:** As a QA engineer, I want caching to only occur when explicitly enabled, so that I have control over which usecases use caching.

#### Acceptance Criteria

1. THE Cache_Builder_Lambda SHALL query the USECASE record (pk: USECASES, sk: USECASE#{usecase_id})
2. THE Cache_Builder_Lambda SHALL check the `enable_cache` field on the USECASE record
3. IF `enable_cache` is false or missing, THEN THE Cache_Builder_Lambda SHALL log the skip reason and return without processing
4. IF the USECASE record does not exist, THEN THE Cache_Builder_Lambda SHALL log an error and return without processing
5. THE Cache_Builder_Lambda SHALL log cache eligibility decisions at INFO level for observability

### Requirement 3: S3 Act File Discovery

**User Story:** As a developer, I want the Lambda to efficiently locate Nova Act response files, so that cache building completes quickly.

#### Acceptance Criteria

1. THE Cache_Builder_Lambda SHALL list S3 objects with prefix `executions/{execution_id}/act_`
2. THE Cache_Builder_Lambda SHALL extract the `act_id` from each S3 key using the pattern `act_{act_id}.json`
3. THE Cache_Builder_Lambda SHALL build a mapping dictionary `{act_id: s3_key}` for efficient lookup
4. IF no S3 objects are found with the prefix, THEN THE Cache_Builder_Lambda SHALL log a warning and return without processing
5. THE Cache_Builder_Lambda SHALL handle S3 access errors gracefully by logging and returning without raising exceptions

### Requirement 4: Execution Step Retrieval

**User Story:** As a developer, I want the Lambda to process only navigation steps, so that cache building focuses on steps that benefit from caching.

#### Acceptance Criteria

1. THE Cache_Builder_Lambda SHALL query EXECUTION_STEP records (pk: EXECUTION#{execution_id}, sk begins_with: EXECUTION_STEP#)
2. THE Cache_Builder_Lambda SHALL filter steps where `step_type` equals `navigation`
3. THE Cache_Builder_Lambda SHALL skip steps where `act_id` is missing or null
4. THE Cache_Builder_Lambda SHALL skip steps where no matching S3 act file exists in the act_id mapping
5. THE Cache_Builder_Lambda SHALL log the count of navigation steps found and the count of steps with matching act files

### Requirement 5: Nova Act Response Parsing

**User Story:** As a developer, I want the Lambda to parse Nova Act responses into cacheable actions, so that steps can be replayed without calling Nova Act.

#### Acceptance Criteria

1. THE Cache_Builder_Lambda SHALL fetch the Nova Act response JSON from S3 using the mapped s3_key
2. THE Cache_Builder_Lambda SHALL invoke `parse_nova_act_steps()` from the Cache_Parser module
3. IF parsing returns None or an empty list, THEN THE Cache_Builder_Lambda SHALL log a warning and skip that step
4. IF parsing raises an exception, THEN THE Cache_Builder_Lambda SHALL log the error and skip that step
5. THE Cache_Builder_Lambda SHALL handle S3 fetch errors gracefully by logging and skipping that step

### Requirement 6: Cache Storage in STEP Records

**User Story:** As a QA engineer, I want cached steps stored in the original STEP records, so that future executions can use the cache.

#### Acceptance Criteria

1. THE Cache_Builder_Lambda SHALL update the original STEP record (pk: USECASE#{usecase_id}, sk: STEP#{step_id})
2. THE Cache_Builder_Lambda SHALL store the parsed cached steps as a JSON string in the `cached_steps` field
3. THE Cache_Builder_Lambda SHALL store the event timestamp in the `cache_last_updated` field
4. THE Cache_Builder_Lambda SHALL use DynamoDB batch_writer for efficient batch updates
5. THE Cache_Builder_Lambda SHALL handle DynamoDB update errors gracefully by logging and continuing to process remaining steps

### Requirement 7: Step ID Resolution

**User Story:** As a developer, I want the Lambda to correctly map execution steps back to their original step templates, so that caches are stored in the correct STEP records.

#### Acceptance Criteria

1. THE Cache_Builder_Lambda SHALL extract the original `step_id` from the EXECUTION_STEP record
2. THE Cache_Builder_Lambda SHALL use the `step_id` field (not the execution_step_id from the sk) to identify the original STEP record
3. IF the `step_id` field is missing from an EXECUTION_STEP, THEN THE Cache_Builder_Lambda SHALL log an error and skip that step
4. THE Cache_Builder_Lambda SHALL construct the STEP record key as pk: USECASE#{usecase_id}, sk: STEP#{step_id}
5. THE Cache_Builder_Lambda SHALL handle cases where the original STEP record no longer exists by logging and continuing

### Requirement 8: Observability and Logging

**User Story:** As a DevOps engineer, I want comprehensive logging, so that I can monitor cache building performance and troubleshoot issues.

#### Acceptance Criteria

1. THE Cache_Builder_Lambda SHALL log the start of processing with usecase_id and execution_id at INFO level
2. THE Cache_Builder_Lambda SHALL log cache eligibility decisions (enabled/disabled, success/failure status) at INFO level
3. THE Cache_Builder_Lambda SHALL log the count of S3 act files found at INFO level
4. THE Cache_Builder_Lambda SHALL log the count of navigation steps processed and cache updates performed at INFO level
5. THE Cache_Builder_Lambda SHALL log all errors (S3, DynamoDB, parsing) at ERROR level with full context
6. THE Cache_Builder_Lambda SHALL log warnings for skipped steps at WARNING level
7. THE Cache_Builder_Lambda SHALL log the completion of processing with summary statistics at INFO level

### Requirement 9: Error Resilience

**User Story:** As a QA engineer, I want cache building failures to not affect test execution, so that caching is a performance optimization without reliability risk.

#### Acceptance Criteria

1. THE Cache_Builder_Lambda SHALL use try-except blocks around all AWS service calls (S3, DynamoDB)
2. IF an error occurs processing one step, THEN THE Cache_Builder_Lambda SHALL log the error and continue processing remaining steps
3. THE Cache_Builder_Lambda SHALL never raise exceptions to the Lambda runtime (all errors caught and logged)
4. THE Cache_Builder_Lambda SHALL return a success response (200) even if some steps fail to process
5. THE Cache_Builder_Lambda SHALL track and log the count of successful updates vs failed updates

### Requirement 10: CDK Infrastructure Configuration

**User Story:** As a developer, I want the Lambda and EventBridge rule defined in CDK, so that infrastructure is version-controlled and reproducible.

#### Acceptance Criteria

1. THE Worker_Stack SHALL define a Lambda function for the Cache_Builder_Lambda
2. THE Worker_Stack SHALL grant the Lambda read access to the S3 execution bucket
3. THE Worker_Stack SHALL grant the Lambda read/write access to the DynamoDB table
4. THE Worker_Stack SHALL define an EventBridge rule matching source `qa-studio.worker` and detail-type `usecase.execution.completed`
5. THE Worker_Stack SHALL configure the EventBridge rule to trigger the Cache_Builder_Lambda
6. THE Worker_Stack SHALL set appropriate Lambda timeout (minimum 60 seconds for batch processing)
7. THE Worker_Stack SHALL set appropriate Lambda memory (minimum 512 MB for JSON parsing)

### Requirement 11: Unit Test Coverage

**User Story:** As a developer, I want comprehensive unit tests, so that cache building logic is reliable and maintainable.

#### Acceptance Criteria

1. THE test suite SHALL mock boto3 clients (S3, DynamoDB) using unittest.mock or moto
2. THE test suite SHALL test successful cache building with valid inputs
3. THE test suite SHALL test skipping non-success executions (execution_status != 'success')
4. THE test suite SHALL test skipping when enable_cache is false
5. THE test suite SHALL test handling missing USECASE records
6. THE test suite SHALL test handling empty S3 act file lists
7. THE test suite SHALL test handling parsing failures (parse_nova_act_steps returns None)
8. THE test suite SHALL test handling S3 fetch errors
9. THE test suite SHALL test handling DynamoDB update errors
10. THE test suite SHALL test batch_writer usage for efficient updates
11. THE test suite SHALL achieve minimum 70% code coverage

### Requirement 12: Integration with Existing Systems

**User Story:** As a developer, I want the Lambda to integrate seamlessly with existing worker and parser modules, so that the cache system works end-to-end.

#### Acceptance Criteria

1. THE Cache_Builder_Lambda SHALL import and use `parse_nova_act_steps()` from `worker.cache_parser` module
2. THE Cache_Builder_Lambda SHALL process events emitted by the Worker's `event_emitter.emit_execution_completed_event()` function
3. THE Cache_Builder_Lambda SHALL read S3 files written by the Worker during test execution
4. THE Cache_Builder_Lambda SHALL update STEP records that are copied to EXECUTION_STEP by `execute_usecase.py`
5. THE Cache_Builder_Lambda SHALL use the same DynamoDB table name from environment variable `DYNAMODB_TABLE_NAME`
6. THE Cache_Builder_Lambda SHALL use the same S3 bucket from environment variable `S3_BUCKET`
