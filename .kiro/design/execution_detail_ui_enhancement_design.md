# Product Design Document: Execution Detail Page UI Enhancement

**Document Version:** 1.0  
**Date:** March 5, 2026  
**Author:** Jan
**Status:** Draft for Review

---

## Executive Summary

This document outlines the design for enhancing the usecase execution detail page UI in the Nova Act QA Studio. The enhancement replaces the current modal-based trace viewing with an expandable section approach, allowing users to view multiple steps simultaneously and scroll through the entire test journey. The recording will also be moved to an expandable section at the execution level.

---

## 1. Current State Analysis

### 1.1 Current Implementation

**File:** `ExecutionSteps.tsx`

**Current Behavior:**
- Steps displayed in a table with columns: Step #, Status, Instruction, Validation
- "Trace" button opens a modal (`modalVisible`) that loads HTML trace file from S3
- Modal displays one step at a time - users must close and reopen to view different steps
- Recording handled separately via `RecordingPlayer` component in a modal
- Each step shows:
  - Status badge (pending, executing, success, error, completed, stopped)
  - Instruction text
  - Trace link (if `actId` is available and not "error" or "cached")
  - Cached badge (blue badge when `actId === "cached"`)
  - Validation results (if present)

**Current Data Flow:**
1. `handleViewFile()` fetches HTML trace from S3 via `getS3FileUrl()`
2. Presigned URL passed to `onViewFile()` callback
3. Modal displays HTML content

**Limitations:**
- Cannot view multiple steps simultaneously
- Must search through steps to understand journey flow
- HTML trace contains redundant information (e.g., prompt section)
- Recording viewing is separate from step viewing

### 1.2 Current Artifacts

**Available per step:**
- HTML trace file: `act_{act_id}_trace.html`
- JSON trace file: `act_{act_id}_calls.json` (contains detailed step information)
- Screenshots (base64 encoded within JSON)
- Logs

**JSON Structure (from example):**
```json
{
  "steps": [
    {
      "step_num": 1,
      "thought": "...",
      "action": "...",
      "screenshot": "base64_encoded_image",
      "time_s": 1.234
    }
  ],
  "metadata": {
    "session_id": "...",
    "act_id": "...",
    "num_steps_executed": 2,
    "start_time": 1772578798.1568685,
    "end_time": 1772578812.1133463,
    "prompt": "...",
    "time_worked_s": 13.956477880477905
  }
}
```

---

## 2. Proposed Solution

### 2.1 High-Level Design

**Key Changes:**
1. Replace modal-based trace viewing with expandable sections (one per step)
2. Use JSON trace instead of HTML trace for denser, more relevant information
3. Display: screenshot, thought process, agent action, and time spent per step
4. Move recording to expandable section at execution level (above or below step list)
5. Add headline/section header above all step expandable sections
6. When collapsed, show: status, cached indicator, instruction, and validation
7. All sections collapsed by default
8. Optional: "Expand All" / "Collapse All" control

### 2.2 Component Hierarchy

```
ExecutionDetailWithLiveView
├── Container (Execution Info)
├── ExpandableSection (Recording) ← NEW
│   └── RecordingPlayer
├── Header ("Test Journey Steps") ← NEW
├── ExpandableSection (Step 1) ← NEW
│   ├── Header (collapsed): Status + Cached + Instruction + Validation
│   └── Content (expanded):
│       ├── Screenshot
│       ├── Thought Process
│       ├── Agent Action
│       └── Time Spent
├── ExpandableSection (Step 2)
│   └── ...
└── ExpandableSection (Step N)
    └── ...
```

### 2.3 UI Layout

#### 2.3.1 Collapsed Step View

```
┌─────────────────────────────────────────────────────────────┐
│ ▶ Step 1: [Success Badge] [Cached Badge] Navigate to login │
│   Validation: Login page loaded successfully                │
└─────────────────────────────────────────────────────────────┘
```

**Elements:**
- Expand/collapse icon (▶/▼)
- Step number
- Status badge (colored indicator)
- Cached badge (if applicable)
- Instruction text
- Validation result (if present)

#### 2.3.2 Expanded Step View

**Desktop Layout (2-column grid):**
```
┌─────────────────────────────────────────────────────────────────────────┐
│ ▼ Step 1: [Success Badge] [Cached Badge] Navigate to login             │
│   Validation: Login page loaded successfully                            │
│                                                                          │
│   ┌──────────────────────────────┬──────────────────────────────────┐  │
│   │ Screenshot                   │ Thought Process:                 │  │
│   │                              │ "I need to locate the login      │  │
│   │ [Base64 decoded image]       │ button and click it..."          │  │
│   │                              │                                  │  │
│   │                              │ Agent Action:                    │  │
│   │                              │ agentClick("login-button")       │  │
│   │                              │                                  │  │
│   │                              │ Time Spent: 1.23s                │  │
│   └──────────────────────────────┴──────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

**Mobile Layout (stacked):**
```
┌─────────────────────────────────────────┐
│ ▼ Step 1: [Success] Navigate to login  │
│   Validation: Login page loaded         │
│                                         │
│   Screenshot                            │
│   [Base64 decoded image]                │
│                                         │
│   Thought Process:                      │
│   "I need to locate the login button    │
│   and click it..."                      │
│                                         │
│   Agent Action:                         │
│   agentClick("login-button")            │
│                                         │
│   Time Spent: 1.23s                     │
└─────────────────────────────────────────┘
```

#### 2.3.3 Recording Section

```
┌─────────────────────────────────────────────────────────────┐
│ ▶ Recording                                                  │
└─────────────────────────────────────────────────────────────┘

(When expanded)
┌─────────────────────────────────────────────────────────────┐
│ ▼ Recording                                                  │
│   [RecordingPlayer component rendered here]                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Technical Implementation

### 3.1 API Changes

**Current:**
- Lambda returns presigned URL for HTML trace file

**Proposed:**
- Lambda returns JSON structure with parsed trace data:

```typescript
interface StepTraceData {
  stepNum: number;
  thought: string;
  action: string;
  screenshot: string; // base64 encoded
  timeSpent: number; // in seconds
}

interface ExecutionStepWithTrace {
  // Existing fields
  sort: number;
  status: string;
  instruction: string;
  actId: string | null;
  stepType: string;
  validation?: any;
  logs?: string;
  
  // New field
  traceData?: StepTraceData;
}
```

**API Endpoint Changes:**
- Modify existing endpoint that fetches execution details
- Instead of returning presigned URL, parse JSON trace and include relevant data
- Handle base64 screenshot decoding/encoding as needed
- Cache parsed data to avoid repeated S3 reads

### 3.2 Component Changes

#### 3.2.1 New Component: `StepExpandableSection.tsx`

```typescript
interface StepExpandableSectionProps {
  step: ExecutionStepWithTrace;
  defaultExpanded?: boolean;
}

export const StepExpandableSection: React.FC<StepExpandableSectionProps> = ({
  step,
  defaultExpanded = false
}) => {
  return (
    <ExpandableSection
      defaultExpanded={defaultExpanded}
      variant="container"
      headerText={
        <StepHeader
          stepNum={step.sort}
          status={step.status}
          isCached={step.actId === "cached"}
          instruction={step.instruction}
          validation={step.validation}
        />
      }
    >
      {step.traceData && (
        <StepTraceContent traceData={step.traceData} />
      )}
    </ExpandableSection>
  );
};
```

#### 3.2.2 New Component: `StepHeader.tsx`

```typescript
interface StepHeaderProps {
  stepNum: number;
  status: string;
  isCached: boolean;
  instruction: string;
  validation?: any;
}

export const StepHeader: React.FC<StepHeaderProps> = ({
  stepNum,
  status,
  isCached,
  instruction,
  validation
}) => {
  return (
    <Box>
      <SpaceBetween direction="horizontal" size="xs">
        <Badge color={getStatusColor(status)}>{status}</Badge>
        {isCached && <Badge color="blue">Cached</Badge>}
        <Box variant="span">Step {stepNum}: {instruction}</Box>
      </SpaceBetween>
      {validation && (
        <Box variant="small" color="text-status-info">
          Validation: {formatValidation(validation)}
        </Box>
      )}
    </Box>
  );
};
```

#### 3.2.3 New Component: `StepTraceContent.tsx`

```typescript
interface StepTraceContentProps {
  traceData: StepTraceData;
}

export const StepTraceContent: React.FC<StepTraceContentProps> = ({
  traceData
}) => {
  return (
    <Grid
      gridDefinition={[
        { colspan: { default: 12, xs: 6 } }, // Screenshot: full width on mobile, half on desktop
        { colspan: { default: 12, xs: 6 } }  // Details: full width on mobile, half on desktop
      ]}
    >
      {/* Left Column: Screenshot */}
      <Container header={<Header variant="h3">Screenshot</Header>}>
        <img 
          src={`data:image/png;base64,${traceData.screenshot}`}
          alt={`Step ${traceData.stepNum} screenshot`}
          style={{ maxWidth: '100%', height: 'auto' }}
        />
      </Container>

      {/* Right Column: Thought, Action, Time */}
      <SpaceBetween size="m">
        <Container header={<Header variant="h3">Thought Process</Header>}>
          <Box variant="p">{traceData.thought}</Box>
        </Container>

        <Container header={<Header variant="h3">Agent Action</Header>}>
          <Box variant="code">{traceData.action}</Box>
        </Container>

        <Container header={<Header variant="h3">Time Spent</Header>}>
          <Box variant="p">{traceData.timeSpent.toFixed(2)}s</Box>
        </Container>
      </SpaceBetween>
    </Grid>
  );
};
```

**Grid Breakpoints:**
- `xs` (extra small): < 688px → stacked layout (12 columns each)
- `default`: ≥ 688px → side-by-side layout (6 columns each)

#### 3.2.4 Modified Component: `ExecutionSteps.tsx`

**Remove:**
- Modal state (`modalVisible`, `modalContent`)
- `handleViewFile()` function
- Modal component

**Add:**
- Section header: "Test Journey Steps"
- Optional "Expand All" / "Collapse All" controls
- Map steps to `StepExpandableSection` components

```typescript
export const ExecutionSteps: React.FC<ExecutionStepsProps> = ({
  steps,
  // ... other props
}) => {
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());

  const handleExpandAll = () => {
    setExpandedSteps(new Set(steps.map(s => s.sort)));
  };

  const handleCollapseAll = () => {
    setExpandedSteps(new Set());
  };

  return (
    <SpaceBetween size="l">
      <Container
        header={
          <Header
            variant="h2"
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                <Button onClick={handleExpandAll}>Expand All</Button>
                <Button onClick={handleCollapseAll}>Collapse All</Button>
              </SpaceBetween>
            }
          >
            Test Journey Steps
          </Header>
        }
      >
        <SpaceBetween size="m">
          {steps.map(step => (
            <StepExpandableSection
              key={step.sort}
              step={step}
              defaultExpanded={expandedSteps.has(step.sort)}
            />
          ))}
        </SpaceBetween>
      </Container>
    </SpaceBetween>
  );
};
```

#### 3.2.5 Modified Component: `ExecutionDetailWithLiveView.tsx`

**Add:**
- Recording expandable section above or below step list

```typescript
<SpaceBetween size="l">
  {/* Existing execution info container */}
  <Container>
    {/* ... execution metadata ... */}
  </Container>

  {/* NEW: Recording Section */}
  {recordingUrl && (
    <ExpandableSection
      variant="container"
      headerText="Recording"
      defaultExpanded={false}
    >
      <RecordingPlayer
        recordingUrl={recordingUrl}
        sessionId={sessionId}
      />
    </ExpandableSection>
  )}

  {/* Modified: Steps with expandable sections */}
  <ExecutionSteps steps={steps} />
</SpaceBetween>
```

### 3.3 Data Flow

```
1. User navigates to execution detail page
   ↓
2. Frontend fetches execution data (including steps)
   ↓
3. Backend Lambda:
   - Fetches execution metadata from DynamoDB
   - For each step with actId:
     - Fetches JSON trace from S3
     - Parses JSON and extracts: screenshot, thought, action, time
     - Includes in response
   ↓
4. Frontend receives enriched step data
   ↓
5. Renders expandable sections (all collapsed by default)
   ↓
6. User expands section → displays trace content
```

---

## 4. UX Flow & Interaction Patterns

### 4.1 User Journey

1. **Page Load:**
   - All expandable sections collapsed
   - User sees overview of all steps with status, instruction, validation
   - Recording section collapsed

2. **Exploring Steps:**
   - User clicks on step to expand
   - Screenshot, thought, action, time displayed
   - User can expand multiple steps simultaneously
   - User scrolls through entire journey

3. **Viewing Recording:**
   - User expands recording section
   - Recording player loads and displays video

4. **Bulk Actions:**
   - User clicks "Expand All" to see all steps at once
   - User clicks "Collapse All" to return to overview

### 4.2 Interaction States

**Step States:**
- **Collapsed:** Shows summary (status, instruction, validation)
- **Expanded:** Shows full trace data (screenshot, thought, action, time)
- **Loading:** Shows spinner while fetching trace data (if lazy-loaded)
- **Error:** Shows error message if trace data unavailable

**Recording States:**
- **Collapsed:** Shows "Recording" header only
- **Expanded:** Shows recording player
- **Loading:** Shows spinner while loading recording
- **Unavailable:** Shows message if no recording available

---

## 5. Edge Cases & Error Handling

### 5.1 Missing Data

| Scenario | Handling |
|----------|----------|
| No `actId` | Don't show expandable section, show "No trace available" |
| `actId === "error"` | Show error state in collapsed view, no expansion |
| `actId === "cached"` | Show cached badge, display cache execution info |
| Missing screenshot | Show placeholder or "Screenshot unavailable" |
| Missing thought/action | Show "Not available" in respective section |
| JSON parse error | Show error message, fallback to HTML trace link |

### 5.2 Performance Considerations

**Large Executions:**
- If execution has 50+ steps, consider:
  - Virtualization (render only visible sections)
  - Lazy loading (fetch trace data on expand)
  - Pagination (show 20 steps at a time)

**Large Screenshots:**
- Compress base64 images on backend
- Use thumbnail in collapsed view, full size on expand
- Lazy load images (only when section expanded)

**Memory Management:**
- Limit number of simultaneously expanded sections (e.g., max 10)
- Auto-collapse sections when scrolled out of view
- Clear image data when section collapsed

### 5.3 Mobile/Responsive Behavior

**Grid Breakpoints:**
- **Mobile (< 688px):** Stacked layout - screenshot on top, details below
- **Desktop (≥ 688px):** Side-by-side layout - screenshot left, details right

**Additional Mobile Optimizations:**
- Reduce screenshot max-width to fit mobile viewport
- Stack thought/action/time vertically with reduced spacing
- Hide "Expand All" button on mobile (too many sections to expand at once)
- Consider accordion-style expansion (collapse others when one expands) to save screen space

**Cloudscape Grid Usage:**
```typescript
<Grid
  gridDefinition={[
    { colspan: { default: 12, xs: 6 } }, // Full width mobile, half desktop
    { colspan: { default: 12, xs: 6 } }  // Full width mobile, half desktop
  ]}
>
  {/* Screenshot column */}
  {/* Details column */}
</Grid>
```

---

## 6. Success Metrics

### 6.1 User Experience Metrics

- **Time to understand test journey:** Reduce by 50% (baseline: time to click through all modals)
- **Number of clicks to view all steps:** Reduce from N*2 (open + close modal) to 1 (expand all)
- **User satisfaction:** Survey users on new UI vs. old UI

### 6.2 Performance Metrics

- **Page load time:** Should not increase by more than 10%
- **Time to first interaction:** Should remain under 2 seconds
- **Memory usage:** Monitor for memory leaks with large executions

### 6.3 Adoption Metrics

- **Feature usage:** Track % of users who expand sections
- **Expand All usage:** Track how often users use "Expand All" button
- **Recording views:** Track % of users who view recording

---

## 7. Implementation Plan

### 7.1 Phase 1: Backend Changes (Week 1)

- [ ] Modify Lambda to parse JSON trace files
- [ ] Add trace data to execution step response
- [ ] Handle base64 screenshot encoding
- [ ] Add error handling for missing/malformed JSON
- [ ] Add caching for parsed trace data
- [ ] Write unit tests for JSON parsing logic

### 7.2 Phase 2: Frontend Components (Week 2)

- [ ] Create `StepExpandableSection` component
- [ ] Create `StepHeader` component
- [ ] Create `StepTraceContent` component
- [ ] Add "Expand All" / "Collapse All" controls
- [ ] Write unit tests for new components

### 7.3 Phase 3: Integration (Week 3)

- [ ] Modify `ExecutionSteps.tsx` to use new components
- [ ] Remove modal-based trace viewing
- [ ] Add recording expandable section to `ExecutionDetailWithLiveView.tsx`
- [ ] Test with various execution scenarios (success, error, cached, missing data)
- [ ] Write integration tests

### 7.4 Phase 4: Polish & Optimization (Week 4)

- [ ] Add lazy loading for trace data (if needed)
- [ ] Optimize screenshot loading
- [ ] Add responsive design for mobile
- [ ] Add loading states and error states
- [ ] Performance testing with large executions
- [ ] User acceptance testing

### 7.5 Phase 5: Deployment & Monitoring (Week 5)

- [ ] Deploy to staging environment
- [ ] Conduct user testing with beta users
- [ ] Gather feedback and iterate
- [ ] Deploy to production
- [ ] Monitor performance metrics
- [ ] Monitor user adoption metrics

---

## 8. Open Questions & Decisions Needed

### 8.1 Answered Questions

✅ **Q: Which information from JSON trace should be displayed?**  
**A:** Screenshot, thought process, agent action, time spent

✅ **Q: Should expandable sections be collapsed by default?**  
**A:** Yes, all collapsed by default

✅ **Q: Should there be "Expand All" / "Collapse All" control?**  
**A:** Yes

✅ **Q: How should recording section integrate?**  
**A:** Separate expandable section at execution level (above or below step list)

✅ **Q: Should screenshots remain in current location?**  
**A:** No, move into expandable sections (from JSON trace)

✅ **Q: Should validation results remain in table?**  
**A:** Yes, show in collapsed view of expandable section

✅ **Q: What about JSON documents for all steps?**  
**A:** JSON trace has always been part of execution artifacts, so all steps should have it

### 8.2 Open Questions

❓ **Q: Should we support fallback to HTML trace if JSON parsing fails?**  
**Recommendation:** Yes, provide link to HTML trace as fallback

❓ **Q: Should we add search/filter functionality for steps?**  
**Recommendation:** Not in MVP, consider for future enhancement

❓ **Q: Should we add export functionality (e.g., export all steps as PDF)?**  
**Recommendation:** Not in MVP, consider for future enhancement

❓ **Q: Should we add keyboard shortcuts (e.g., arrow keys to navigate steps)?**  
**Recommendation:** Not in MVP, consider for future enhancement

---

## 9. Future Enhancements

### 9.1 Short-term (Next Quarter)

- Add search/filter functionality for steps
- Add step comparison (diff between two steps)
- Add step annotations (user comments on steps)
- Add step bookmarking (mark important steps)

### 9.2 Long-term (Next Year)

- Add AI-powered insights (e.g., "This step took longer than usual")
- Add step replay (re-run specific step)
- Add step editing (modify and re-run)
- Add collaborative features (share specific steps with team)
- Add export functionality (PDF, JSON, CSV)

---

## 10. Appendix

### 10.1 Cloudscape ExpandableSection Reference

**Component:** `ExpandableSection`  
**Documentation:** https://cloudscape.design/components/expandable-section/

**Key Props:**
- `variant`: "default" | "container" | "footer" | "navigation"
- `defaultExpanded`: boolean
- `expanded`: boolean (controlled)
- `onChange`: (event) => void
- `headerText`: ReactNode
- `headerActions`: ReactNode
- `children`: ReactNode

**Example:**
```tsx
<ExpandableSection
  variant="container"
  defaultExpanded={false}
  headerText="Step 1: Navigate to login"
>
  <Box>Content here</Box>
</ExpandableSection>
```

### 10.2 JSON Trace Structure Reference

```json
{
  "steps": [
    {
      "step_num": 1,
      "thought": "I need to close any popups...",
      "action": "agentClick('close-button')",
      "screenshot": "iVBORw0KGgoAAAANSUhEUgAA...",
      "time_s": 1.234
    }
  ],
  "metadata": {
    "session_id": "019cb5ed-db08-7eeb-b484-5f130bedba4b",
    "act_id": "019cb5ed-fa09-7b6d-a6ec-1c9d52537d8e",
    "num_steps_executed": 2,
    "start_time": 1772578798.1568685,
    "end_time": 1772578812.1133463,
    "prompt": "Close any popups on the page",
    "time_worked_s": 13.956477880477905
  }
}
```

### 10.3 Status Badge Colors

| Status | Color |
|--------|-------|
| pending | grey |
| executing | blue |
| success | green |
| error | red |
| completed | green |
| stopped | grey |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-05 | AI Assistant | Initial draft based on user requirements |

---

**Next Steps:**
1. Review this document with stakeholders
2. Gather feedback and iterate
3. Prioritize features for MVP
4. Begin implementation (Phase 1)
