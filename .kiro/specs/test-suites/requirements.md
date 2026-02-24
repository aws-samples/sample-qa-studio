# Requirements Document

## Introduction

This document specifies the requirements for the Test Suites feature, which enables users to group multiple use cases into test suites and execute them as a batch with real-time status tracking.

## Glossary

- **Test_Suite**: A logical grouping of use cases that can be executed together as a batch
- **Suite_Execution**: A single run of all use cases within a test suite
- **Use_Case**: An individual test scenario that can be executed independently or as part of a suite
- **Scope**: An OAuth permission string that controls access to resources (format: `api/suite.read` or `api/suite.write`)
- **Parallel_Execution**: Simultaneous execution of multiple use cases without waiting for each to complete
- **Execution_Result**: The outcome of a single use case execution within a suite execution
- **Admin_Scope**: Special scope `api/admin` that bypasses all other authorization checks

## Requirements

### Requirement 1: Test Suite Management

**User Story:** As a QA engineer, I want to create and manage test suites, so that I can organize related use cases into logical groups.

#### Acceptance Criteria

1. WHEN a user creates a test suite, THE System SHALL store the suite with a unique identifier, name, description, and tags (scope is optional and auto-generated from suite name if not provided)
2. WHEN a user lists test suites, THE System SHALL return all suites the user has read access to based on their scopes
3. WHEN a user views a test suite, THE System SHALL display the suite metadata including total use cases and last execution status
4. WHEN a user updates a test suite, THE System SHALL modify the suite metadata and update the timestamp
5. WHEN a user deletes a test suite, THE System SHALL remove the suite, all use case mappings, and disable any configured schedule

### Requirement 2: Use Case Association

**User Story:** As a QA engineer, I want to add use cases to test suites, so that I can build comprehensive test scenarios.

#### Acceptance Criteria

1. WHEN a user adds use cases to a suite, THE System SHALL create mappings between the suite and each use case
2. WHEN a user adds a use case already in the suite, THE System SHALL treat it as a no-op (idempotent operation)
3. WHEN a user lists use cases in a suite, THE System SHALL return all associated use cases with their metadata
4. WHEN a user removes a use case from a suite, THE System SHALL delete the mapping and decrement the total use case count
5. WHERE a use case belongs to multiple suites, WHEN the use case is deleted, THE System SHALL remove it from all suites

### Requirement 3: Parallel Suite Execution

**User Story:** As a QA engineer, I want to execute all use cases in a suite simultaneously, so that I can get test results faster.

#### Acceptance Criteria

1. WHEN a user executes a test suite, THE System SHALL spawn ECS tasks for all use cases in parallel
2. WHEN a suite execution starts, THE System SHALL create a suite execution record with status 'running'
3. WHEN individual use cases complete, THE System SHALL update their execution results independently
4. IF a use case fails, THEN THE System SHALL continue executing other use cases in the suite
5. WHEN all use cases complete, THE System SHALL update the suite execution status to 'completed' or 'partial'

### Requirement 4: Real-Time Status Tracking

**User Story:** As a QA engineer, I want to monitor suite execution progress in real-time, so that I can see which tests are passing or failing as they run.

#### Acceptance Criteria

1. WHEN a suite execution is running, THE System SHALL track the count of completed, successful, failed, and running use cases
2. WHEN a use case execution completes, THE System SHALL update the suite execution counters atomically
3. WHEN a user queries suite execution status, THE System SHALL return current status for all use cases in the suite
4. WHEN all use cases finish with no failures, THE System SHALL set suite execution status to 'completed'
5. WHEN all use cases finish with some failures, THE System SHALL set suite execution status to 'partial'

### Requirement 5: Scope-Based Access Control

**User Story:** As a system administrator, I want to control access to test suites using OAuth scopes, so that I can enforce security policies.

#### Acceptance Criteria

1. WHEN a user creates a suite, THE System SHALL validate the user has `api/suite.write` scope or `api/admin` scope
2. WHEN a user views a suite, THE System SHALL validate the user has `api/suite.read` scope or `api/admin` scope
3. WHEN a user executes a suite, THE System SHALL validate the user has `api/suite.write` scope or `api/admin` scope
4. WHEN a user adds a use case to a suite, THE System SHALL validate the user has `api/suite.write` scope or `api/admin` scope
5. WHERE a user lacks required permissions, THE System SHALL return an authorization error
6. WHEN a user has `api/admin` scope, THE System SHALL bypass all other scope checks

### Requirement 6: Suite Scheduling

**User Story:** As a QA engineer, I want to schedule test suites to run automatically, so that I can ensure regular test coverage without manual intervention.

#### Acceptance Criteria

1. WHEN a user configures a suite schedule, THE System SHALL create an EventBridge rule with the specified cron expression
2. WHEN a schedule is enabled, THE System SHALL execute the suite automatically at the scheduled times
3. WHEN a scheduled execution triggers, THE System SHALL record the trigger type as 'scheduled'
4. WHEN a user disables a schedule, THE System SHALL disable the EventBridge rule without deleting it
5. WHEN a suite is deleted, THE System SHALL remove any associated EventBridge rules

### Requirement 7: Suite Metrics and Dashboard

**User Story:** As a QA manager, I want to see suite metrics at a glance, so that I can quickly assess test health.

#### Acceptance Criteria

1. WHEN a suite execution completes, THE System SHALL update denormalized metrics on the suite entity
2. WHEN a user lists suites, THE System SHALL display total use cases, last execution status, and last successful count
3. WHEN a user views suite detail, THE System SHALL show the last 10 executions with their status and metrics
4. THE System SHALL store last_execution_id, last_execution_status, last_execution_time, and last_successful_count on each suite
5. THE System SHALL calculate and display success rate as a ratio of successful to total use cases

### Requirement 8: Execution Control

**User Story:** As a QA engineer, I want suite executions to run to completion, so that I can see all test results.

#### Acceptance Criteria

1. WHEN a suite execution starts, THE System SHALL execute all use cases to completion
2. WHEN individual use cases complete, THE System SHALL update their execution results independently
3. THE System SHALL NOT provide a mechanism to stop running suite executions
4. WHEN all use cases complete, THE System SHALL update the suite execution status to 'completed', 'partial', or 'failed'
5. THE System SHALL allow users to view execution progress in real-time
6. WHEN a user stops an individual use case execution that is part of a suite, THE System SHALL treat it as a failed execution and update suite counters accordingly

### Requirement 9: Execution History

**User Story:** As a QA engineer, I want to view historical suite executions, so that I can track test trends over time.

#### Acceptance Criteria

1. WHEN a user lists suite executions, THE System SHALL return executions sorted by start time descending
2. WHEN listing executions, THE System SHALL support pagination with a configurable limit
3. WHEN listing executions, THE System SHALL support filtering by execution status
4. WHEN a user views an execution, THE System SHALL display detailed results for each use case including duration and error messages
5. THE System SHALL store execution metadata including started_at, completed_at, duration_seconds, and trigger_type

### Requirement 10: Data Model Integrity

**User Story:** As a system architect, I want a robust data model for test suites, so that the system can scale and maintain data consistency.

#### Acceptance Criteria

1. THE System SHALL use a many-to-many relationship allowing use cases to belong to multiple suites
2. THE System SHALL denormalize frequently accessed data (use case names, suite names) for read performance
3. THE System SHALL use atomic counter updates for suite execution metrics to prevent race conditions
4. THE System SHALL use separate partition key prefixes for suite executions to avoid conflicts with use case executions
5. THE System SHALL maintain referential integrity by cleaning up mappings when suites or use cases are deleted
