# Bugfix Requirements Document

## Introduction

When a usecase execution runs through the qa-studio-ci-runner path (`qa-studio-ci-runner/src/execution/engine.py`), the Nova Act session ID is never captured or persisted to the execution record in DynamoDB. This means the `nova_session_id` field remains empty, which breaks downstream features that depend on it — specifically the recording/video playback and trace log retrieval in the frontend (`ExecutionInformation.tsx`) and the S3 URL generation endpoint (`generate_s3_url.py`).

The worker path (`worker/wizard_worker.py`) correctly calls `nova.get_session_id()` after opening the NovaAct context and persists it via `db_client.update_execution_session_id()`. The qa-studio-ci-runner path does neither.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a usecase execution runs through the qa-studio-ci-runner path (`ExecutionEngine._run_steps_with_nova`) THEN the system never calls `nova.get_session_id()` after opening the NovaAct context, so the Nova Act session ID is not captured.

1.2 WHEN a usecase execution runs through the qa-studio-ci-runner path THEN the system never updates the DynamoDB execution record with the `nova_session_id` field, because `ExecutionAPI` has no method to persist the session ID via the API.

1.3 WHEN a user views the execution detail for a qa-studio-ci-runner execution in the frontend THEN the Nova Act session ID is empty and the recording link is unavailable, because `nova_session_id` was never written to the record.

1.4 WHEN the S3 URL generation endpoint (`generate_s3_url.py`) attempts to build an artifact URL for a qa-studio-ci-runner execution THEN it fails with the error `No Nova Act session ID found for execution: {execution_id}`, because the `nova_session_id` field is missing from the execution record. Observed for execution `019c76ba-728d-fa40-f224-eae7164fd2b4`.

### Expected Behavior (Correct)

2.1 WHEN a usecase execution runs through the qa-studio-ci-runner path (`ExecutionEngine._run_steps_with_nova`) THEN the system SHALL call `nova.get_session_id()` immediately after the NovaAct context is opened to capture the session ID.

2.2 WHEN the qa-studio-ci-runner captures a Nova Act session ID THEN the system SHALL update the execution record in DynamoDB with the `nova_session_id` field via an API call (PATCH endpoint on the execution resource).

2.3 WHEN a user views the execution detail for a qa-studio-ci-runner execution in the frontend THEN the Nova Act session ID SHALL be present and the recording link SHALL be available.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a usecase execution runs through the worker/wizard path (`wizard_worker.py`) THEN the system SHALL CONTINUE TO capture the Nova Act session ID via `nova.get_session_id()` and persist it via `db_client.update_execution_session_id()`.

3.2 WHEN the qa-studio-ci-runner executes steps via `_run_steps_with_nova` THEN the system SHALL CONTINUE TO execute all steps sequentially, report step statuses, capture artifacts, and handle failures identically to current behavior.

3.3 WHEN the existing PATCH `/api/usecases/{id}/executions/{executionId}/status` endpoint is called THEN the system SHALL CONTINUE TO update execution status, timestamps, and error messages as before.

3.4 WHEN `nova.get_session_id()` fails or returns None in the qa-studio-ci-runner THEN the system SHALL CONTINUE TO execute the test steps without interruption (session ID capture failure must not be fatal).
