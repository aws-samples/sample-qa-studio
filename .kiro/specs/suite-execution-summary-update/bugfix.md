# Bugfix Requirements Document

## Introduction

When a test suite is executed via the CI/CD runner, the test suite summary record (`TEST_SUITES/SUITE#{suite_id}`) is never updated with the latest execution results. The CI/CD runner calls the `update_suite_execution_status` endpoint after all use cases complete, but this endpoint only updates the suite execution record's status — it does not propagate the results back to the test suite record. As a result, the frontend shows stale or missing data for `last_execution_status`, `last_execution_time`, and `last_execution_id` on test suites that were executed via the CI/CD runner.

Additionally, the suite execution counters (`completed_usecases`, `successful_usecases`, `failed_usecases`, `running_usecases`) on the suite execution record are never updated during the CI/CD runner flow. The `update_execution_status` endpoint (called per-usecase) does not touch suite execution counters, and the CI/CD runner sends the final suite status directly without counter updates. This means the suite execution detail view shows `0` for completed/successful/failed counts even after all use cases have finished.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a CI/CD runner completes a suite execution and calls the `update_suite_execution_status` endpoint with a terminal status (`completed`, `partial`, or `failed`), THEN the system updates the suite execution record status but does NOT update the test suite summary record (`TEST_SUITES/SUITE#{suite_id}`) with `last_execution_status`, `last_execution_time`, `last_execution_id`, `last_successful_count`, or `last_failed_count`

1.2 WHEN a CI/CD runner updates individual use case execution status via the `update_execution_status` endpoint, THEN the system does NOT update the suite execution counters (`completed_usecases`, `successful_usecases`, `failed_usecases`, `running_usecases`) on the suite execution record, leaving them at their initial values (e.g. `completed_usecases=0`, `running_usecases=N`)

1.3 WHEN a CI/CD runner completes a suite execution and the `update_suite_execution_status` endpoint is called, THEN the system does NOT set `last_execution_id` on the test suite record, so the frontend cannot link to the most recent suite execution

### Expected Behavior (Correct)

2.1 WHEN a CI/CD runner completes a suite execution and calls the `update_suite_execution_status` endpoint with a terminal status (`completed`, `partial`, or `failed`), THEN the system SHALL also update the test suite summary record (`TEST_SUITES/SUITE#{suite_id}`) with `last_execution_status` (set to the suite execution status), `last_execution_time` (set to the current timestamp), `last_execution_id` (set to the suite execution ID), `last_successful_count`, and `last_failed_count` derived from the suite execution's counters

2.2 WHEN a CI/CD runner updates individual use case execution status to a terminal status (`success` or `failed`) via the `update_execution_status` endpoint, THEN the system SHALL atomically update the suite execution counters on the suite execution record — incrementing `completed_usecases` and the appropriate success/failure counter, and decrementing `running_usecases`

2.3 WHEN a CI/CD runner completes a suite execution and the `update_suite_execution_status` endpoint is called with a terminal status, THEN the system SHALL set `last_execution_id` on the test suite record to the suite execution ID that just completed

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a use case execution is NOT part of a suite (no `suite_execution_id` on the execution record), THEN the system SHALL CONTINUE TO update the execution status without attempting suite counter tracking

3.2 WHEN the `update_suite_execution_status` endpoint receives a non-terminal status (`running`), THEN the system SHALL CONTINUE TO update only the suite execution record status without touching the test suite summary record

3.3 WHEN the `update_suite_execution_status` endpoint is called for a non-existent suite execution, THEN the system SHALL CONTINUE TO return a 404 error

3.4 WHEN the ECS worker path updates suite execution tracking, THEN the system SHALL CONTINUE TO function independently of the CI/CD runner path changes
