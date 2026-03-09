# Requirements Document

## Introduction

This feature enhances the execution detail page by replacing modal-based trace viewing with inline expandable sections. A new backend endpoint fetches and parses JSON trace files from S3, returning structured trace data per step. The frontend renders each execution step as a Cloudscape ExpandableSection with lazy-loaded trace content (screenshot, thought process, agent action, time spent). The recording player is moved from a modal into an expandable section at the execution level. Users can view multiple steps simultaneously, use Expand All / Collapse All controls, and scroll through the entire test journey.

## Glossary

- **Execution_Detail_Page**: The frontend page that displays execution metadata, steps, and recording for a single test execution
- **Step_Expandable_Section**: A Cloudscape ExpandableSection component representing a single execution step, showing summary when collapsed and full trace data when expanded
- **Trace_Data**: Structured JSON data from S3 containing sub-steps with thought process, agent action, screenshot, and time spent
- **Step_Header**: The collapsed header content showing step number, status, cached badge, instruction, and validation result
- **Step_Trace_Content**: The expanded content area showing screenshot and trace details in a responsive grid layout
- **Get_Step_Trace_Endpoint**: The new Lambda endpoint that fetches and parses JSON trace files from S3 for a given execution step
- **Trace_Parser**: The function that parses raw JSON trace file content into validated Pydantic models
- **Execution_Steps_Component**: The modified frontend component that renders steps as expandable sections instead of a table
- **Recording_Section**: An expandable section at the execution level containing the RecordingPlayer component
- **Act_ID**: The Nova Act identifier for a step, used to locate the JSON trace file in S3; special values "cached" and "error" indicate no trace is available

## Requirements

### Requirement 1: Step Trace Data Retrieval

**User Story:** As a QA engineer, I want to retrieve structured trace data for individual execution steps, so that I can inspect the agent's thought process, actions, and screenshots without loading HTML trace files.

#### Acceptance Criteria

1. WHEN a GET request is made to `/usecase/{id}/executions/{executionId}/steps/{stepId}/trace` with a valid `api/executions.read` scope, THE Get_Step_Trace_Endpoint SHALL return a 200 response containing `trace_steps` and `metadata` fields
2. WHEN the Get_Step_Trace_Endpoint receives a request, THE Get_Step_Trace_Endpoint SHALL look up the execution step in DynamoDB to obtain the `act_id`
3. WHEN the Get_Step_Trace_Endpoint has the `act_id`, THE Get_Step_Trace_Endpoint SHALL look up the execution record in DynamoDB to obtain the `nova_session_id`
4. WHEN the Get_Step_Trace_Endpoint has both `act_id` and `nova_session_id`, THE Get_Step_Trace_Endpoint SHALL fetch the JSON trace file from S3 at path `{usecaseId}/{executionId}/{sessionId}/act_{actId}_calls.json`
5. WHEN the JSON trace file is fetched, THE Get_Step_Trace_Endpoint SHALL parse the JSON and return a response with `trace_steps` (array of sub-steps) and `metadata` (act-level metadata)

### Requirement 2: Step Trace Data Validation

**User Story:** As a developer, I want trace data to be validated using Pydantic models, so that the API returns consistent and well-structured responses.

#### Acceptance Criteria

1. THE Trace_Parser SHALL validate each trace sub-step contains `step_num`, `thought`, `action`, `screenshot`, and `time_s` fields
2. THE Trace_Parser SHALL validate metadata contains `session_id`, `act_id`, `num_steps_executed`, `start_time`, `end_time`, `prompt`, and `time_worked_s` fields
3. WHEN the JSON trace file contains valid data, THE Trace_Parser SHALL return a validated `StepTraceResponse` Pydantic model
4. WHEN the JSON trace file is malformed or missing required fields, THE Trace_Parser SHALL raise a `ValueError`

### Requirement 3: Trace Endpoint Error Handling

**User Story:** As a developer, I want the trace endpoint to handle error cases gracefully, so that the frontend receives descriptive error responses instead of 500 errors.

#### Acceptance Criteria

1. WHEN required path parameters (`id`, `executionId`, `stepId`) are missing, THE Get_Step_Trace_Endpoint SHALL return a 400 response with error message "Missing required parameters"
2. WHEN the execution step is not found in DynamoDB, THE Get_Step_Trace_Endpoint SHALL return a 404 response with error message "Execution step not found"
3. WHEN the execution record is not found in DynamoDB, THE Get_Step_Trace_Endpoint SHALL return a 404 response with error message "Execution not found"
4. WHEN the step has no `act_id`, THE Get_Step_Trace_Endpoint SHALL return a 404 response with error message "No trace available for this step"
5. WHEN the step has `act_id` equal to "cached", THE Get_Step_Trace_Endpoint SHALL return a 404 response with error message "No trace available for cached step"
6. WHEN the step has `act_id` equal to "error", THE Get_Step_Trace_Endpoint SHALL return a 404 response with error message "No trace available for errored step"
7. WHEN the JSON trace file is not found in S3, THE Get_Step_Trace_Endpoint SHALL return a 404 response with error message "Trace file not found"
8. WHEN the JSON trace file is malformed, THE Get_Step_Trace_Endpoint SHALL return a 404 response with error message "Failed to parse trace data"
9. IF an unexpected S3 access error occurs, THEN THE Get_Step_Trace_Endpoint SHALL return a 500 response with error message "Internal server error"

### Requirement 4: Trace Endpoint Authorization

**User Story:** As a security engineer, I want the trace endpoint to enforce OAuth scope validation, so that only authorized users can access trace data.

#### Acceptance Criteria

1. WHEN a request is made without a valid `api/executions.read` scope, THE Get_Step_Trace_Endpoint SHALL return a 403 response
2. THE Get_Step_Trace_Endpoint SHALL validate the scope using the existing `require_scopes` function before processing the request
3. THE Get_Step_Trace_Endpoint SHALL NOT expose S3 presigned URLs to the frontend for JSON trace files

### Requirement 5: Step Display as Expandable Sections

**User Story:** As a QA engineer, I want execution steps displayed as expandable sections instead of a table, so that I can view multiple steps simultaneously and scroll through the entire test journey.

#### Acceptance Criteria

1. WHEN the Execution_Detail_Page loads, THE Execution_Steps_Component SHALL render each step as a collapsed Step_Expandable_Section
2. WHEN a step is collapsed, THE Step_Header SHALL display the step number, status icon, instruction text, cached badge (when `act_id` is "cached"), and validation result (when present)
3. WHEN a step is collapsed, THE Step_Header SHALL use the existing `StatusIndicatorCompact` component for the status icon
4. WHEN a step is collapsed and has validation data, THE Step_Header SHALL use the existing `ValidationResult` component to display the validation result
5. THE Execution_Steps_Component SHALL display a "Test Journey Steps" header above all step sections

### Requirement 6: Step Expansion and Trace Loading

**User Story:** As a QA engineer, I want to expand a step to see its trace data loaded on demand, so that the page loads quickly and only fetches data I need.

#### Acceptance Criteria

1. WHEN a user expands a Step_Expandable_Section that has a valid `act_id`, THE Step_Expandable_Section SHALL fetch trace data from the Get_Step_Trace_Endpoint
2. WHILE trace data is being fetched, THE Step_Trace_Content SHALL display a loading spinner
3. WHEN trace data is successfully fetched, THE Step_Trace_Content SHALL display the screenshot, thought process, agent action, and time spent for each trace sub-step
4. IF trace data fetch fails, THEN THE Step_Trace_Content SHALL display an error alert message
5. WHEN a step has been expanded and trace data was successfully fetched, THE Step_Expandable_Section SHALL cache the trace data in local component state
6. WHEN a previously expanded step is collapsed and re-expanded, THE Step_Expandable_Section SHALL display the cached trace data without making another API call

### Requirement 7: Expand All and Collapse All Controls

**User Story:** As a QA engineer, I want to expand or collapse all steps at once, so that I can quickly view the complete journey or return to the overview.

#### Acceptance Criteria

1. THE Execution_Steps_Component SHALL display "Expand All" and "Collapse All" buttons in the header actions area
2. WHEN the user clicks "Expand All", THE Execution_Steps_Component SHALL set all step sections to expanded state
3. WHEN the user clicks "Collapse All", THE Execution_Steps_Component SHALL set all step sections to collapsed state
4. WHEN "Expand All" is clicked, THE Execution_Steps_Component SHALL only trigger trace data fetches for steps with a valid `act_id` (not "cached", not "error", not null)
5. THE Execution_Steps_Component SHALL use controlled expansion state (a set of expanded step IDs) to manage which sections are open

### Requirement 8: Responsive Trace Content Layout

**User Story:** As a QA engineer, I want the trace content to display in a responsive layout, so that I can view it on both desktop and mobile devices.

#### Acceptance Criteria

1. WHEN a step is expanded on desktop (viewport width >= 688px), THE Step_Trace_Content SHALL display the screenshot and details in a 2-column Grid layout (screenshot left, details right)
2. WHEN a step is expanded on mobile (viewport width < 688px), THE Step_Trace_Content SHALL stack the screenshot above the details in a single column
3. WHEN a trace sub-step has a missing screenshot, THE Step_Trace_Content SHALL display a placeholder or "Screenshot unavailable" message
4. WHEN a trace sub-step has a missing thought or action, THE Step_Trace_Content SHALL display "Not available" in the respective section

### Requirement 9: Recording in Expandable Section

**User Story:** As a QA engineer, I want the recording player in an expandable section on the execution detail page, so that I can reference individual step details while watching the recording.

#### Acceptance Criteria

1. WHEN the execution has a recording URL, THE Execution_Detail_Page SHALL display a "Recording" expandable section containing the RecordingPlayer component
2. WHEN the Execution_Detail_Page loads, THE Recording_Section SHALL be collapsed by default
3. THE Execution_Detail_Page SHALL NOT display a recording modal or a "View" recording button in the execution information section
4. WHEN the execution has no recording URL, THE Execution_Detail_Page SHALL NOT display the Recording_Section

### Requirement 10: Removal of Modal-Based Trace Viewing

**User Story:** As a developer, I want the modal-based trace viewing removed, so that the codebase is clean and there is a single consistent way to view trace data.

#### Acceptance Criteria

1. THE Execution_Steps_Component SHALL NOT contain modal state variables (`modalVisible`, `modalContent`)
2. THE Execution_Steps_Component SHALL NOT contain the `handleViewFile` function or `onViewFile` prop
3. THE Execution_Detail_Page SHALL NOT contain recording modal state (`recordingModalVisible`) or HTML trace modal state
4. THE ExecutionInformation component SHALL NOT contain a "View" recording button or `onViewRecording` prop

### Requirement 11: Backend Unit Testing

**User Story:** As a developer, I want comprehensive unit tests for the trace endpoint, so that I can verify correctness without deploying to AWS.

#### Acceptance Criteria

1. THE test suite SHALL verify the happy path: valid step with JSON trace in S3 returns 200 with parsed data
2. THE test suite SHALL verify missing path parameters return 400
3. THE test suite SHALL verify step not found returns 404
4. THE test suite SHALL verify execution not found returns 404
5. THE test suite SHALL verify step with `act_id` "cached" returns 404
6. THE test suite SHALL verify step with `act_id` "error" returns 404
7. THE test suite SHALL verify step with no `act_id` returns 404
8. THE test suite SHALL verify JSON trace file not in S3 returns 404
9. THE test suite SHALL verify malformed JSON in S3 returns 404
10. THE test suite SHALL verify S3 `ClientError` returns 500
11. THE test suite SHALL verify missing scope returns 403
12. THE test suite SHALL verify `parse_trace_json` with valid JSON returns correct `StepTraceResponse`
13. THE test suite SHALL verify `parse_trace_json` with missing fields raises `ValueError`
14. THE test suite SHALL use mocked boto3 clients (DynamoDB and S3) to avoid AWS dependencies

### Requirement 12: Frontend Unit Testing

**User Story:** As a developer, I want unit tests for the new frontend components, so that I can verify UI behavior and prevent regressions.

#### Acceptance Criteria

1. THE test suite SHALL verify Step_Expandable_Section renders collapsed with correct header content (status, instruction, cached badge)
2. THE test suite SHALL verify Step_Expandable_Section fetches trace data on expand
3. THE test suite SHALL verify Step_Expandable_Section shows loading spinner while fetching
4. THE test suite SHALL verify Step_Expandable_Section shows trace content after successful fetch
5. THE test suite SHALL verify Step_Expandable_Section shows error message on fetch failure
6. THE test suite SHALL verify Step_Expandable_Section does not re-fetch on collapse/expand cycle
7. THE test suite SHALL verify Execution_Steps_Component renders all steps as expandable sections
8. THE test suite SHALL verify "Expand All" expands all sections
9. THE test suite SHALL verify "Collapse All" collapses all sections
