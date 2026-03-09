# Implementation Plan: Execution Detail UI Enhancement

## Overview

This plan replaces the modal-based trace viewing on the execution detail page with inline expandable sections. A new `get_step_trace` Lambda endpoint fetches and parses JSON trace files from S3, returning structured trace data per step. The frontend renders each execution step as a Cloudscape ExpandableSection with lazy-loaded trace content. The recording player moves from a modal into an expandable section. Backend tasks come first (the frontend depends on the API), followed by frontend components, then integration and cleanup.

## Tasks

- [x] 1. Create `get_step_trace` Lambda endpoint with Pydantic models and trace parsing
  - [x] 1.1 Create `web-app/lambdas/endpoints/get_step_trace.py` with Pydantic models and handler
    - Define `TraceStep`, `TraceMetadata`, `StepTraceResponse` Pydantic models
    - Implement `parse_trace_json(raw_json: str) -> StepTraceResponse` function that parses JSON and validates via Pydantic; raises `ValueError` on malformed/missing fields
    - Implement `handler(event, context)` Lambda handler:
      - Validate `api/executions.read` scope via `require_scopes`
      - Extract `id`, `executionId`, `stepId` from `event['pathParameters']`
      - Return 400 if any path parameter is missing
      - Look up execution step in DynamoDB (`pk: EXECUTION#{executionId}`, `sk: EXECUTION_STEP#{stepId}`) to get `act_id`
      - Return 404 if step not found, or if `act_id` is `None`, `"cached"`, or `"error"` (with descriptive messages)
      - Look up execution in DynamoDB (`pk: USECASE_EXECUTION#{usecaseId}`, `sk: EXECUTION#{executionId}`) to get `nova_session_id`
      - Return 404 if execution not found
      - Fetch `{usecaseId}/{executionId}/{sessionId}/act_{actId}_calls.json` from S3
      - Return 404 if S3 `NoSuchKey`, return 404 with "Failed to parse trace data" if JSON is malformed
      - Return 500 on unexpected S3 errors
      - Return 200 with `trace.model_dump()` on success
    - Use existing `create_response`, `get_table_name`, `require_scopes` from `utils.py`
    - Add `BUCKET_NAME` environment variable reading via `os.environ`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.1, 4.2, 4.3_

  - [ ]* 1.2 Write unit tests for `get_step_trace` Lambda
    - Create `web-app/lambdas/endpoints/test_get_step_trace.py`
    - Mock `boto3.resource` (DynamoDB table) and `boto3.client` (S3) and `require_scopes`
    - Test happy path: valid step with JSON trace in S3 → 200 with parsed `trace_steps` and `metadata`
    - Test missing path parameters → 400
    - Test step not found in DynamoDB → 404
    - Test execution not found in DynamoDB → 404
    - Test step with `act_id = "cached"` → 404
    - Test step with `act_id = "error"` → 404
    - Test step with no `act_id` → 404
    - Test JSON trace file not in S3 (`NoSuchKey`) → 404
    - Test malformed JSON in S3 → 404
    - Test S3 `ClientError` (non-NoSuchKey) → 500
    - Test missing scope → 403 (mock `require_scopes` returning error)
    - Test `parse_trace_json` with valid JSON → correct `StepTraceResponse`
    - Test `parse_trace_json` with missing fields → `ValueError`
    - Test `parse_trace_json` with empty steps array → valid response with empty list
    - Aim for 70%+ coverage on `get_step_trace.py`
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 11.10, 11.11, 11.12, 11.13, 11.14_

  - [ ]* 1.3 Write property test for trace data completeness
    - **Property 1: Trace data completeness**
    - **Validates: Requirements 1.1, 1.5, 2.1, 2.2, 2.3**
    - Generate random valid JSON trace structures using `hypothesis`
    - Verify `parse_trace_json` returns `StepTraceResponse` with all required fields present in every `TraceStep` and in `metadata`
    - Run minimum 100 iterations

  - [ ]* 1.4 Write property test for non-traceable act_id rejection
    - **Property 3: Non-traceable act_id rejection**
    - **Validates: Requirements 3.4, 3.5, 3.6**
    - Generate random `act_id` values including `None`, `"cached"`, `"error"`, empty string using `hypothesis`
    - Mock DynamoDB to return steps with these `act_id` values
    - Verify handler returns 404 with descriptive error message for each
    - Run minimum 100 iterations

  - [ ]* 1.5 Write property test for JSON parse error resilience
    - **Property 4: JSON parse error resilience**
    - **Validates: Requirements 2.4, 3.8**
    - Generate random malformed JSON strings using `hypothesis` (text strategy)
    - Verify `parse_trace_json` raises `ValueError` (never an unhandled exception)
    - Run minimum 100 iterations

  - [ ]* 1.6 Write property test for S3 key construction correctness
    - **Property 5: S3 key construction correctness**
    - **Validates: Requirement 1.4**
    - Generate random `usecaseId`, `executionId`, `sessionId`, `actId` strings using `hypothesis`
    - Mock DynamoDB and S3, capture the S3 key used in `get_object`
    - Verify key matches pattern `{usecaseId}/{executionId}/{sessionId}/act_{actId}_calls.json`
    - Run minimum 100 iterations

- [x] 2. Add CDK wiring for `get_step_trace` Lambda
  - [x] 2.1 Add Lambda definition in `web-app/lib/lambda-stack.ts`
    - Add `public readonly getStepTraceLambda: Function` property
    - Create Lambda using `createPythonLambda` with path `'get_step_trace'`
    - Set environment variables: `TABLE_NAME` (table name) and `BUCKET_NAME` (artefacts bucket name)
    - Grant S3 read access to artefacts bucket
    - Grant DynamoDB read access via `tableReadPolicy`
    - _Requirements: 1.1, 4.1, 4.2_

  - [x] 2.2 Add API Gateway route in `web-app/lib/api-stack.ts`
    - Add `GET /usecase/{id}/executions/{executionId}/steps/{stepId}/trace` route
    - Wire to `getStepTraceLambda`
    - The `{stepId}` resource already exists; add a `trace` sub-resource under it
    - _Requirements: 1.1, 4.1_

- [x] 3. Checkpoint - Backend complete
  - Run `pytest web-app/lambdas/endpoints/test_get_step_trace.py -v`
  - Verify all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Create new frontend components for step expandable sections
  - [x] 4.1 Create `StepHeader` component at `web-app/frontend/src/components/execution/StepHeader.tsx`
    - Accept props: `stepNum`, `status`, `isCached`, `instruction`, `stepType`, `validation` (optional)
    - Display step number and instruction text
    - Show status icon using existing `StatusIndicatorCompact` component
    - Show "Cached" `Badge` (color blue) when `isCached` is true
    - Show validation result using existing `ValidationResult` component when validation data is present
    - Handle `download` step type showing "Downloaded: {actual_value}"
    - Show logs via `<pre>` when present (matching current table behavior)
    - _Requirements: 5.2, 5.3, 5.4_

  - [x] 4.2 Create `StepTraceContent` component at `web-app/frontend/src/components/execution/StepTraceContent.tsx`
    - Accept props: `traceSteps` (array), `loading` (boolean), `error` (string | null)
    - Show Cloudscape `Spinner` while `loading` is true
    - Show Cloudscape `Alert` with error message when `error` is set
    - For each trace sub-step, render a responsive `Grid` layout:
      - Left column (screenshot): `colspan: { default: 12, m: 6 }` — render `<img>` with `data:image/png;base64,{screenshot}`, show "Screenshot unavailable" placeholder if missing
      - Right column (details): `colspan: { default: 12, m: 6 }` — show thought process, agent action (in code style), and time spent
    - Handle missing thought/action with "Not available" text
    - _Requirements: 6.2, 6.3, 6.4, 8.1, 8.2, 8.3, 8.4_

  - [x] 4.3 Create `StepExpandableSection` component at `web-app/frontend/src/components/execution/StepExpandableSection.tsx`
    - Accept props: `step`, `expanded`, `onExpandChange`, `usecaseId`, `executionId`
    - Use Cloudscape `ExpandableSection` with `variant="container"` and controlled `expanded` prop
    - Render `StepHeader` as the header content
    - Determine `hasTrace`: step has `act_id` and it's not `"cached"` and not `"error"`
    - On expand: if `hasTrace` and no cached trace data, fetch from `GET usecase/{usecaseId}/executions/{executionId}/steps/{step.sort}/trace`
    - Cache fetched trace data in local `useState` to avoid re-fetching on collapse/expand
    - Show `StepTraceContent` with loading/error/data states
    - For cached steps (no trace), show "Cached" info when expanded
    - For error steps (no trace), show error info when expanded
    - Include `CopyToClipboard` for act ID (preserving existing functionality)
    - _Requirements: 5.1, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 5. Modify `ExecutionSteps` to use expandable sections
  - [x] 5.1 Replace table with expandable sections in `web-app/frontend/src/components/execution/ExecutionSteps.tsx`
    - Remove: `Table` component, `loadingModal` state, `handleViewFile` function, `onViewFile` prop, `getS3FileUrl` import
    - Add: `expandedSteps` state (`Set<number>`) for controlled expansion
    - Add: `traceDataCache` consideration (cache lives in each `StepExpandableSection`)
    - Add: "Test Journey Steps" `Header` with "Expand All" / "Collapse All" `Button`s in `actions`
    - Map `executionSteps` to `StepExpandableSection` components, passing `expanded` and `onExpandChange`
    - "Expand All" sets all step `sort` values in `expandedSteps`
    - "Collapse All" clears `expandedSteps`
    - Update `ExecutionStepsProps` interface: remove `onViewFile`, keep `usecaseId` and `executionId`
    - _Requirements: 5.1, 5.5, 7.1, 7.2, 7.3, 7.4, 7.5, 10.1, 10.2_

- [x] 6. Modify `ExecutionDetailRefactored` and `ExecutionInformation`
  - [x] 6.1 Update `ExecutionDetailRefactored` at `web-app/frontend/src/components/ExecutionDetailRefactored.tsx`
    - Remove: `modalVisible` state, `modalContent` state, `recordingModalVisible` state, `handleViewContent` function, `handleViewRecording` function
    - Remove: HTML trace `Modal` component (iframe modal)
    - Remove: Recording `Modal` component
    - Keep: `stopModalVisible` modal (unrelated to this feature)
    - Remove: `onViewFile` prop from `ExecutionSteps` usage
    - Remove: `onViewRecording` prop from `ExecutionInformation` usage
    - Add: Recording `ExpandableSection` (collapsed by default) containing `RecordingPlayer`, rendered only when execution has a recording URL (terminal status: success, failed, error, stopped)
    - Remove unused imports: `Modal` (if only used for trace/recording), `RecordingPlayer` import stays
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 10.3, 10.4_

  - [x] 6.2 Update `ExecutionInformation` at `web-app/frontend/src/components/execution/ExecutionInformation.tsx`
    - Remove: `onViewRecording` prop from interface
    - Remove: "Recording" → "View" button from `KeyValuePairs` items
    - Remove: `Button` import if no longer used
    - _Requirements: 10.4_

  - [x] 6.3 Update `ExecutionDetailWithLiveView` at `web-app/frontend/src/components/execution/ExecutionDetailWithLiveView.tsx`
    - Remove: `onViewFile` prop from interface and from `ExecutionSteps` usage
    - _Requirements: 10.2_

  - [x] 6.4 Update barrel export at `web-app/frontend/src/components/execution/index.ts`
    - Verify exports are correct after component changes
    - No new exports needed (new components are internal to the execution folder)
    - _Requirements: 10.1, 10.2_

- [x] 7. Checkpoint - Frontend components complete
  - Verify the app compiles without errors (`npm run build` in frontend)
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Write frontend unit tests
  - [ ]* 8.1 Write tests for `StepExpandableSection` at `web-app/frontend/src/components/execution/__tests__/StepExpandableSection.test.tsx`
    - Test renders collapsed with correct header content (status, instruction, cached badge)
    - Test expands and fetches trace data on click (mock `api.get`)
    - Test shows loading spinner while fetching
    - Test shows trace content after successful fetch
    - Test shows error message on fetch failure
    - Test does not re-fetch on collapse/expand cycle (cache works)
    - Test handles step with no `act_id` (no trace fetch)
    - Test handles cached step (shows badge, no trace fetch)
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [ ]* 8.2 Write tests for `ExecutionSteps` at `web-app/frontend/src/components/execution/__tests__/ExecutionSteps.test.tsx`
    - Test renders all steps as expandable sections
    - Test "Expand All" expands all sections
    - Test "Collapse All" collapses all sections
    - Test Expand All only fetches trace for steps with valid `act_id`
    - _Requirements: 12.7, 12.8, 12.9_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Run backend tests: `pytest web-app/lambdas/endpoints/test_get_step_trace.py -v`
  - Run frontend tests: `npm test` in frontend directory
  - Verify no regressions in existing tests
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using `hypothesis` library (minimum 100 iterations)
- Backend uses Python with boto3, Pydantic for models; frontend uses TypeScript with Cloudscape components
- The new endpoint reuses the existing `api/executions.read` scope — no new OAuth scopes needed
- DynamoDB items use snake_case field names; API Gateway path parameters use snake_case per CDK definitions
- The `{stepId}` API Gateway resource already exists under `steps`; only a `trace` sub-resource needs to be added
- S3 key pattern: `{usecaseId}/{executionId}/{sessionId}/act_{actId}_calls.json`
- Existing components reused: `StatusIndicatorCompact`, `ValidationResult`, `RecordingPlayer`, `CopyToClipboard`
