---
title: Wizard Mode - Interactive Use Case Builder
status: draft
created: 2024-11-28
---

# Wizard Mode - Interactive Use Case Builder

## Overview

Wizard mode allows users to build use cases interactively with a live browser view. Users add steps one at a time, see them execute in real-time, and accept steps before they're saved. This provides immediate feedback and makes it easier to build and debug test workflows.

## User Flow

1. User creates new use case via "Wizard" option (same initial fields as "Create blank")
2. System launches wizard interface with:
   - **Top section**: Live browser view (reusing existing execution detail live view)
   - **Bottom section**: Step builder form (same as existing step dialog)
3. User adds a step → step executes immediately → live view updates
4. User reviews the result and clicks "Accept" button
5. Accepted step is saved to DynamoDB and appears in the steps list
6. User continues adding steps or closes wizard
7. If a step fails or user wants to retry:
   - User can restart execution from beginning
   - Execution replays all accepted steps up to the last one
   - User can then continue from that point

## Architecture

### High-Level Flow

```
Frontend (Wizard UI)
    ↓ REST API
Lambda (Wizard Commands)
    ↓ Write to DynamoDB + Send to SQS
SQS Queue (Step Commands)
    ↓
ECS Task (Wizard Worker - Long-running)
    ↓ Polls SQS
    ↓ Executes step in persistent browser
    ↓ Updates DynamoDB with result
    ↑
Frontend polls DynamoDB for step status + live view URL
```

### Components

#### 1. Frontend Changes

**New Route**: `/usecases/:id/wizard`

**UI Layout**:
- Top 60%: Live browser view (iframe with Bedrock Agent Core live view URL)
- Bottom 40%: Split into two columns
  - Left: Step builder form (reuse existing step dialog fields)
  - Right: Accepted steps list with status indicators

**New Components**:
- `WizardView.tsx` - Main wizard container
- `WizardStepBuilder.tsx` - Step creation form
- `WizardStepsList.tsx` - List of accepted steps
- `WizardLiveView.tsx` - Browser view wrapper

**User Actions**:
- Add Step → Calls `POST /api/wizard/:sessionId/step`
- Accept Step → Calls `POST /api/wizard/:sessionId/accept/:stepId`
- Restart → Calls `POST /api/wizard/:sessionId/restart`
- Close Wizard → Calls `POST /api/wizard/:sessionId/terminate`

**Polling**:
- Poll DynamoDB every 2 seconds for:
  - Current step execution status
  - Live view URL
  - Step results

#### 2. Backend Changes

**New Lambda Functions**:

1. **`start_wizard_session`** - `POST /api/usecases/:id/wizard/start`
   - Creates wizard execution record in DynamoDB with `mode: "wizard"`
   - Starts ECS task in wizard mode
   - Returns sessionId (executionId)

2. **`add_wizard_step`** - `POST /api/wizard/:sessionId/step`
   - Validates step data
   - Creates temporary step record with status `pending_acceptance`
   - Sends SQS message: `{action: "execute_step", sessionId, step}`
   - Returns stepId

3. **`accept_wizard_step`** - `POST /api/wizard/:sessionId/accept/:stepId`
   - Updates step status to `accepted`
   - Saves step to use case in DynamoDB
   - Returns success

4. **`restart_wizard`** - `POST /api/wizard/:sessionId/restart`
   - Sends SQS message: `{action: "restart", sessionId}`
   - Worker will replay all accepted steps
   - Returns success

5. **`terminate_wizard_session`** - `POST /api/wizard/:sessionId/terminate`
   - Sends SQS message: `{action: "terminate", sessionId}`
   - Marks session as closed
   - ECS task will terminate gracefully
   - Returns success

**New SQS Queue**: `wizard-commands-queue`
- Message types:
  - `execute_step`: Execute a single step
  - `restart`: Restart from beginning, replay accepted steps
  - `terminate`: Close wizard session

**DynamoDB Schema Changes**:

New attributes for Execution records:
```
{
  mode: "wizard" | "batch",  // New field
  wizard_status: "active" | "closed",  // For wizard mode only
  last_activity: "2024-11-28T10:30:00Z"  // For timeout tracking
}
```

New attributes for ExecutionStep records:
```
{
  acceptance_status: "pending_acceptance" | "accepted" | "rejected",
  temporary: true | false  // True for steps not yet accepted
}
```

#### 3. Worker Changes

**New File**: `worker/wizard_worker.py`

Key differences from batch worker:
- Starts browser immediately (no steps loaded initially)
- Polls SQS queue for commands with long polling (20s)
- Maintains persistent browser session
- Executes steps on demand
- Handles restart command by replaying accepted steps
- 30-minute inactivity timeout
- Graceful termination on close command

**Reused Logic**:
- All step execution functions (`execute_navigation_step`, `execute_validation_step`, etc.)
- Template parser for variable substitution
- S3Writer for screenshots
- DynamoDB client for status updates
- Bedrock Agent Core browser management

**Worker Modes**:
```python
# Environment variable determines mode
WORKER_MODE = os.getenv('WORKER_MODE', 'batch')  # 'batch' or 'wizard'

if WORKER_MODE == 'wizard':
    wizard_worker.main()
else:
    # Existing batch worker logic
    main()
```

**Wizard Worker Flow**:
```python
1. Initialize browser session
2. Store live view URL in DynamoDB
3. Enter command loop:
   while True:
       - Poll SQS for commands (20s long polling)
       - If no message and last_activity > 30min: terminate
       - Handle command:
         * execute_step: Run step, update DynamoDB
         * restart: Close browser, replay accepted steps
         * terminate: Clean up and exit
       - Update last_activity timestamp
4. On exit: Close browser, delete live view URL
```

#### 4. Infrastructure Changes (CDK)

**New Resources**:
- SQS Queue: `wizard-commands-queue`
- Lambda functions (5 new)
- IAM permissions for wizard lambdas

**Modified Resources**:
- Task definition: Add `WORKER_MODE` environment variable
- Task role: Grant SQS receive permissions for wizard queue

## Implementation Tasks

### Phase 1: Backend Foundation
- [ ] Create wizard SQS queue in CDK
- [ ] Implement `start_wizard_session` Lambda
- [ ] Implement `add_wizard_step` Lambda
- [ ] Implement `accept_wizard_step` Lambda
- [ ] Implement `restart_wizard` Lambda
- [ ] Implement `terminate_wizard_session` Lambda
- [ ] Update DynamoDB schema (add new attributes)

### Phase 2: Worker Implementation
- [ ] Create `wizard_worker.py`
- [ ] Implement SQS polling loop
- [ ] Implement step execution handler (reuse existing functions)
- [ ] Implement restart handler (replay accepted steps)
- [ ] Implement terminate handler
- [ ] Add inactivity timeout logic
- [ ] Update main worker entry point to support mode selection

### Phase 3: Frontend Implementation
- [ ] Create wizard route and main container
- [ ] Implement live view component (reuse existing)
- [ ] Implement step builder form
- [ ] Implement accepted steps list
- [ ] Add polling logic for status updates
- [ ] Implement accept/restart/close actions
- [ ] Add error handling and user feedback

### Phase 4: Testing & Polish
- [ ] Test full wizard flow end-to-end
- [ ] Test restart functionality
- [ ] Test timeout behavior
- [ ] Test error scenarios
- [ ] Add loading states and animations
- [ ] Add user guidance/tooltips
- [ ] Performance optimization

## Technical Considerations

### Browser Session Management
- Use Bedrock Agent Core for persistent browser sessions
- Browser stays alive between steps
- On restart: Close current browser, create new one, replay steps
- Timeout after 30 minutes of inactivity to prevent resource leaks

### Error Handling
- Step execution errors: Mark step as failed, allow user to retry or restart
- Worker crashes: EventBridge monitors task state, updates execution status
- Timeout: Worker self-terminates, updates status to "timeout"
- Network issues: SQS visibility timeout ensures messages aren't lost

### Cost Optimization
- Wizard sessions limited to 30 minutes
- Only one wizard session per user at a time (optional)
- ECS task uses Fargate Spot for cost savings (optional)
- Automatic cleanup of abandoned sessions

### Security
- Validate sessionId belongs to authenticated user
- Rate limiting on wizard API endpoints
- Sanitize step instructions before execution

## Open Questions

1. Should we limit concurrent wizard sessions per user?
2. Should wizard mode support all step types or start with a subset?
3. Do we need real-time updates (WebSocket) or is polling sufficient?
4. Should we auto-save wizard progress in case of browser refresh?
5. Should restart create a new browser or reuse the existing one?

## Success Criteria

- Users can create use cases interactively with live feedback
- Step execution is visible in real-time
- Restart functionality works reliably
- No resource leaks from abandoned sessions
- Performance is acceptable (< 3s step execution feedback)
- Error messages are clear and actionable
