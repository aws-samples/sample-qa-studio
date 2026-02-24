# Design Document

## Overview

The Instruction Optimizer feature integrates AI-powered text optimization into the existing shared form component architecture. The design follows a modular approach where optimization capabilities are added as an optional enhancement to form fields without disrupting existing functionality. The feature uses Amazon Bedrock's Claude model to analyze and improve test instructions, presenting results in a modal dialog that requires explicit user acceptance.

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React)                         │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Shared Form Component                                 │ │
│  │  ├─ FormField (renders OptimizeButton conditionally)  │ │
│  │  └─ OptimizationProvider (context)                    │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Instruction Optimizer Feature Module                 │ │
│  │  ├─ Components (OptimizeButton, Modal, Comparison)    │ │
│  │  ├─ Hooks (useOptimizeInstruction, useHistory)        │ │
│  │  ├─ Services (optimizationApi, bedrockClient)         │ │
│  │  └─ Utils (rateLimiter, cache, sanitizer)             │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ HTTPS
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     Backend API (Lambda)                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  POST /api/usecase/{id}/steps/{id}/optimize           │ │
│  │  ├─ Input validation                                   │ │
│  │  ├─ Authentication check                               │ │
│  │  └─ Bedrock client invocation                          │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ AWS SDK
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Amazon Bedrock                             │
│  Model: anthropic.claude-3-5-sonnet-20241022-v2:0          │
└─────────────────────────────────────────────────────────────┘
```

### Component Structure

```
frontend/src/
├── components/
│   └── shared/
│       ├── Form.tsx                    # Modified: Add OptimizationProvider
│       └── FormField.tsx               # Modified: Render OptimizeButton conditionally
│
└── features/
    └── instruction-optimizer/
        ├── components/
        │   ├── OptimizeButton.tsx      # AI icon button
        │   ├── OptimizationModal.tsx   # Accept/Reject dialog
        │   └── ComparisonView.tsx      # Side-by-side diff view
        ├── hooks/
        │   ├── useOptimizeInstruction.ts
        │   └── useOptimizationHistory.ts
        ├── services/
        │   ├── optimizationApi.ts      # API client
        │   └── bedrockClient.ts        # Bedrock integration
        ├── utils/
        │   ├── rateLimiter.ts          # Client-side rate limiting
        │   ├── cache.ts                # Optimization result cache
        │   └── sanitizer.ts            # PII removal
        ├── store/
        │   └── optimizationSlice.ts    # State management
        ├── types/
        │   └── optimization.types.ts   # TypeScript interfaces
        └── index.ts                    # Public exports

lambda/cmd/
└── optimize_instruction/
    └── main.go                         # Lambda handler for optimization
```

## Components and Interfaces

### Frontend Components

#### 1. OptimizeButton Component

**Purpose**: Renders an AI icon button next to optimizable form fields

**Props**:
```typescript
interface OptimizeButtonProps {
  fieldName: string;
  currentValue: string;
  context: OptimizationContext;
  onAccepted: (value: string) => void;
}
```

**States**:
- `idle`: Default state, AI icon visible
- `loading`: Spinner overlay on icon
- `disabled`: Grayed out (empty or short text)

**Behavior**:
- Disabled when `currentValue.length < 10`
- On click: calls `useOptimizeInstruction` hook
- On success: opens `OptimizationModal`
- On error: displays error toast

#### 2. OptimizationModal Component

**Purpose**: Displays side-by-side comparison and requires explicit user action

**Props**:
```typescript
interface OptimizationModalProps {
  isOpen: boolean;
  original: string;
  optimized: string;
  suggestions: string[];
  onAccept: (text: string) => void;
  onReject: () => void;
}
```

**Layout**:
- Header: "Optimized Instruction"
- Body: `<ComparisonView />` component
- Footer: "Accept" and "Reject" buttons

**Behavior**:
- ESC key triggers `onReject`
- Click outside triggers `onReject`
- "Accept" button triggers `onAccept` with optimized text
- "Reject" button triggers `onReject`

#### 3. ComparisonView Component

**Purpose**: Shows original vs optimized text with diff highlighting

**Props**:
```typescript
interface ComparisonViewProps {
  original: string;
  optimized: string;
  suggestions: string[];
}
```

**Features**:
- Two-column grid layout
- Diff highlighting (red for removed, green for added)
- Character count for both versions
- Suggestions list below optimized text

### Backend Components

#### Lambda Handler: optimize_instruction

**Endpoint**: `POST /api/usecase/{useCaseId}/steps/{stepId}/optimize`

**Request**:
```json
{
  "instruction": "string (max 2000 chars)"
}
```

**Response**:
```json
{
  "original": "string",
  "optimized": "string",
  "suggestions": ["string", "string", ...]
}
```

**Error Responses**:
- `400`: Invalid input (empty, too long, etc.)
- `429`: Rate limit exceeded
- `500`: Bedrock service error
- `504`: Timeout (>30s)

**Processing Flow**:
1. Validate authentication
2. Validate input (length, content)
3. Call Bedrock with prompt
4. Parse response
5. Return structured result

## Data Models

### TypeScript Interfaces

```typescript
// Form field configuration extension
interface FormFieldConfig {
  name: string;
  type: 'text' | 'textarea' | 'select';
  label: string;
  optimizable?: boolean;
  optimizationContext?: OptimizationContext;
}

interface OptimizationContext {
  useCaseId: string;
  stepId: string;
}

interface OptimizationRequest {
  instruction: string;
}

interface OptimizationResponse {
  original: string;
  optimized: string;
  suggestions: string[];
}

interface OptimizationHistory {
  instructionId: string;
  testCaseId: string;
  stepId: string;
  originalText: string;
  optimizedText: string;
  appliedAt: string;
  optimizationMetadata: {
    model: string;
    suggestions: string[];
    tokenUsage?: number;
  };
}

interface OptimizationState {
  isOptimizing: boolean;
  result: OptimizationResponse | null;
  error: string | null;
  history: OptimizationHistory[];
}

interface CacheEntry {
  result: OptimizationResponse;
  timestamp: number;
}

interface RateLimitState {
  requests: number[];
  limit: number;
  window: number;
}
```

### Go Structs

```go
type OptimizeInstructionRequest struct {
    Instruction string `json:"instruction"`
}

type OptimizeInstructionResponse struct {
    Original    string   `json:"original"`
    Optimized   string   `json:"optimized"`
    Suggestions []string `json:"suggestions"`
}

type BedrockRequest struct {
    Prompt            string  `json:"prompt"`
    MaxTokens         int     `json:"max_tokens"`
    Temperature       float64 `json:"temperature"`
    TopP              float64 `json:"top_p"`
    StopSequences     []string `json:"stop_sequences"`
}

type BedrockResponse struct {
    Content []struct {
        Text string `json:"text"`
    } `json:"content"`
    Usage struct {
        InputTokens  int `json:"input_tokens"`
        OutputTokens int `json:"output_tokens"`
    } `json:"usage"`
}
```


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Button disabled for short text

*For any* instruction text with length less than 10 characters, the AI optimization button should be disabled.

**Validates: Requirements 1.2**

### Property 2: Diff highlighting correctness

*For any* pair of original and optimized text strings, the diff highlighting should correctly identify all additions (shown in green) and removals (shown in red).

**Validates: Requirements 2.3**

### Property 3: Rejection preserves original value

*For any* original instruction value, after a user rejects the optimization (via Reject button, ESC key, or outside click), the instruction field value should remain unchanged.

**Validates: Requirements 2.5**

### Property 4: Rate limiter tracks requests accurately

*For any* sequence of optimization requests, the rate limiter should accurately count the number of requests within the current time window.

**Validates: Requirements 3.1**

### Property 5: Optimizable flag controls button rendering

*For any* form field configuration with optimizable flag set to true, the system should render an AI optimization button; for any field without the flag or with it set to false, no button should render.

**Validates: Requirements 4.1, 4.2**

### Property 6: Optimizable fields require context

*For any* form field marked as optimizable, the configuration must include optimizationContext with both useCaseId and stepId, otherwise validation should fail.

**Validates: Requirements 4.3**

### Property 7: Cache stores optimization results

*For any* instruction text and optimization result, after a successful optimization, the cache should contain an entry with the instruction as key and the result as value.

**Validates: Requirements 5.1**

### Property 8: Cache lookup before API call

*For any* instruction text that exists in cache with a valid (non-expired) entry, requesting optimization should return the cached result without making an API call.

**Validates: Requirements 5.2**

### Property 9: Cache TTL enforcement

*For any* cached result, if the entry timestamp is less than 1 hour old, it should be returned; if older than 1 hour, it should be evicted and a new API call should be made.

**Validates: Requirements 5.3, 5.4**

### Property 10: History persistence for accepted optimizations

*For any* optimization that a user accepts, the system should save a history record containing original text, optimized text, and metadata to local storage.

**Validates: Requirements 6.1**

### Property 11: History size limit enforcement

*For any* optimization history, when the number of entries exceeds 100, the system should remove the oldest entries to maintain the limit.

**Validates: Requirements 6.3**

### Property 12: History includes timestamp and context

*For any* saved optimization history entry, it should include a timestamp and the use case context (useCaseId and stepId).

**Validates: Requirements 6.5**

### Property 15: Email sanitization

*For any* instruction text containing email address patterns, the sanitizer should replace all email addresses with the placeholder "[EMAIL]" before sending to Bedrock.

**Validates: Requirements 7.1**

### Property 16: Phone number sanitization

*For any* instruction text containing phone number patterns, the sanitizer should replace all phone numbers with the placeholder "[PHONE]" before sending to Bedrock.

**Validates: Requirements 7.2**

### Property 17: SSN sanitization

*For any* instruction text containing social security number patterns, the sanitizer should replace all SSNs with the placeholder "[SSN]" before sending to Bedrock.

**Validates: Requirements 7.3**

### Property 18: Length truncation

*For any* instruction text exceeding 2000 characters, the sanitizer should truncate it to exactly 2000 characters before sending to Bedrock.

**Validates: Requirements 7.4**

### Property 19: Sanitization preserves original

*For any* instruction text, after sanitization is applied, the original user input should remain unmodified in the form field.

**Validates: Requirements 7.5**

## Error Handling

### Client-Side Error Handling

**Empty or Short Instructions**:
- Button disabled state (grayed out)
- Tooltip on hover: "Enter at least 10 characters to optimize"
- No API call made

**Rate Limit Exceeded**:
- Error toast: "Too many requests. Please wait a moment."
- Button disabled for 60 seconds
- Client-side countdown timer

**Network Errors**:
- Error toast: "Network error. Please check your connection."
- Button returns to default state
- User can retry immediately

**API Errors**:
- 400 Bad Request: "Invalid instruction. Please provide clear text."
- 429 Too Many Requests: "Too many requests. Please wait a moment."
- 500 Internal Server Error: "Optimization service unavailable. Try again later."
- 504 Gateway Timeout: "Optimization took too long. Please try again."

**Timeout (30s)**:
- Error toast: "Optimization took too long. Please try again."
- Button returns to default state
- Request cancelled on client side

### Backend Error Handling

**Input Validation**:
```go
func validateInstruction(instruction string) error {
    if len(strings.TrimSpace(instruction)) == 0 {
        return errors.New("instruction cannot be empty")
    }
    if len(instruction) > 2000 {
        return errors.New("instruction exceeds maximum length of 2000 characters")
    }
    return nil
}
```

**Bedrock API Errors**:
- Retry logic: 3 attempts with exponential backoff
- Circuit breaker: After 5 consecutive failures, stop calling Bedrock for 5 minutes
- Fallback: Return error to client with appropriate status code

**Timeout Handling**:
- Lambda timeout: 30 seconds
- Bedrock client timeout: 25 seconds
- Return 504 Gateway Timeout if exceeded

## Testing Strategy

### Unit Tests

**Frontend Unit Tests**:

1. **OptimizeButton Component**:
   - Renders AI icon in default state
   - Disables when text length < 10 characters
   - Shows loading spinner during optimization
   - Calls optimization hook on click
   - Displays error toast on failure

2. **OptimizationModal Component**:
   - Renders with correct props
   - Calls onAccept when Accept button clicked
   - Calls onReject when Reject button clicked
   - Calls onReject when ESC key pressed
   - Calls onReject when clicking outside modal

3. **ComparisonView Component**:
   - Renders original and optimized text
   - Highlights differences correctly
   - Displays suggestions list
   - Shows character counts

4. **useOptimizeInstruction Hook**:
   - Returns loading state during optimization
   - Returns result on success
   - Returns error on failure
   - Checks cache before API call
   - Stores result in cache after success

5. **Rate Limiter**:
   - Tracks requests correctly
   - Blocks requests when limit exceeded
   - Resets after time window
   - Allows requests after reset

6. **Cache**:
   - Stores entries with correct key
   - Returns cached entries within TTL
   - Evicts entries after TTL
   - Handles cache misses

7. **Sanitizer**:
   - Replaces email addresses
   - Replaces phone numbers
   - Replaces SSNs
   - Truncates long text
   - Preserves original input

**Backend Unit Tests**:

1. **Lambda Handler**:
   - Validates authentication
   - Validates input
   - Calls Bedrock client
   - Returns correct response format
   - Handles errors appropriately

2. **Bedrock Client**:
   - Constructs correct request
   - Parses response correctly
   - Handles API errors
   - Implements retry logic
   - Respects timeout

### Property-Based Tests

**Property Testing Library**: fast-check (for TypeScript/JavaScript)

**Configuration**: Minimum 100 iterations per property test

**Property Tests**:

1. **Property 1: Button disabled for short text**
   - Generate random strings of length 0-9
   - Verify button is disabled for all
   - **Feature: instruction-optimizer, Property 1: Button disabled for short text**

2. **Property 2: Diff highlighting correctness**
   - Generate random pairs of strings
   - Verify diff correctly identifies all changes
   - **Feature: instruction-optimizer, Property 2: Diff highlighting correctness**

3. **Property 3: Rejection preserves original value**
   - Generate random instruction values
   - Simulate rejection
   - Verify value unchanged
   - **Feature: instruction-optimizer, Property 3: Rejection preserves original value**

4. **Property 4: Rate limiter tracks requests accurately**
   - Generate random sequences of requests
   - Verify count is accurate
   - **Feature: instruction-optimizer, Property 4: Rate limiter tracks requests accurately**

5. **Property 5: Optimizable flag controls button rendering**
   - Generate random field configurations
   - Verify button renders only when optimizable=true
   - **Feature: instruction-optimizer, Property 5: Optimizable flag controls button rendering**

6. **Property 6: Optimizable fields require context**
   - Generate field configs with/without context
   - Verify validation fails without context
   - **Feature: instruction-optimizer, Property 6: Optimizable fields require context**

7. **Property 7: Cache stores optimization results**
   - Generate random instructions and results
   - Verify cache contains entries after optimization
   - **Feature: instruction-optimizer, Property 7: Cache stores optimization results**

8. **Property 8: Cache lookup before API call**
   - Generate random cached instructions
   - Verify no API call for cached entries
   - **Feature: instruction-optimizer, Property 8: Cache lookup before API call**

9. **Property 9: Cache TTL enforcement**
   - Generate cache entries with various timestamps
   - Verify TTL logic is correct
   - **Feature: instruction-optimizer, Property 9: Cache TTL enforcement**

10. **Property 10: Analytics tracking for requests**
    - Generate random optimization requests
    - Verify all have analytics events
    - **Feature: instruction-optimizer, Property 10: Analytics tracking for requests**

11. **Property 11: Metrics collection for successful optimizations**
    - Generate random successful optimizations
    - Verify metrics are recorded
    - **Feature: instruction-optimizer, Property 11: Metrics collection for successful optimizations**

12. **Property 12: History persistence for accepted optimizations**
    - Generate random accepted optimizations
    - Verify history records exist
    - **Feature: instruction-optimizer, Property 12: History persistence for accepted optimizations**

13. **Property 13: Rejection tracking without history**
    - Generate random rejected optimizations
    - Verify analytics event but no history
    - **Feature: instruction-optimizer, Property 13: Rejection tracking without history**

14. **Property 14: Error tracking**
    - Generate random failed optimizations
    - Verify error details recorded
    - **Feature: instruction-optimizer, Property 14: Error tracking**

15. **Property 15: Email sanitization**
    - Generate random strings with email patterns
    - Verify all emails replaced
    - **Feature: instruction-optimizer, Property 15: Email sanitization**

16. **Property 16: Phone number sanitization**
    - Generate random strings with phone patterns
    - Verify all phones replaced
    - **Feature: instruction-optimizer, Property 16: Phone number sanitization**

17. **Property 17: SSN sanitization**
    - Generate random strings with SSN patterns
    - Verify all SSNs replaced
    - **Feature: instruction-optimizer, Property 17: SSN sanitization**

18. **Property 18: Length truncation**
    - Generate random strings > 2000 chars
    - Verify truncation to exactly 2000
    - **Feature: instruction-optimizer, Property 18: Length truncation**

19. **Property 19: Sanitization preserves original**
    - Generate random instructions
    - Apply sanitization
    - Verify original unchanged
    - **Feature: instruction-optimizer, Property 19: Sanitization preserves original**

### Integration Tests

1. **End-to-End Optimization Flow**:
   - User enters instruction
   - Clicks optimize button
   - Modal opens with results
   - User accepts
   - Field updates with optimized text

2. **Cache Integration**:
   - First optimization makes API call
   - Second identical optimization uses cache
   - Expired cache triggers new API call

3. **Rate Limiting Integration**:
   - Make 10 requests successfully
   - 11th request blocked
   - After 60 seconds, requests allowed again

4. **Error Handling Integration**:
   - Network error shows appropriate toast
   - API error shows appropriate toast
   - Timeout shows appropriate toast

## Security Considerations

### Input Sanitization

All user input is sanitized before being sent to Bedrock:

1. **PII Removal**:
   - Email addresses → `[EMAIL]`
   - Phone numbers → `[PHONE]`
   - Social Security Numbers → `[SSN]`

2. **Length Limiting**:
   - Maximum 2000 characters
   - Truncate if exceeded

3. **Content Validation**:
   - No script tags
   - No SQL injection patterns
   - No command injection patterns

### Authentication

All API requests require valid authentication:
- JWT token in Authorization header
- Token validated on backend
- User ID extracted from token for tracking

### Rate Limiting

Multiple layers of rate limiting:
- Client-side: 10 requests per minute
- Backend: 20 requests per minute per user
- AWS API Gateway: 100 requests per second (burst)

### Data Privacy

- No instruction text stored permanently
- History records encrypted at rest
- Analytics data anonymized
- Bedrock requests logged without PII

## Performance Considerations

### Response Time Targets

- Cache hit: < 100ms
- API call: < 10 seconds (p95)
- Modal render: < 200ms

### Optimization Strategies

1. **Caching**:
   - Client-side cache for 1 hour
   - Reduces API calls by ~30%
   - Improves response time for repeated instructions

2. **Request Debouncing**:
   - Prevent accidental double-clicks
   - 500ms debounce on optimize button

3. **Lazy Loading**:
   - Load optimization feature module on demand
   - Reduces initial bundle size

4. **Code Splitting**:
   - Separate chunk for optimization components
   - Only loaded when needed

### Client-Side Tracking

Track these metrics locally in the browser:
- Optimization request count (session-based)
- Cache hit rate (session-based)
- Acceptance rate (session-based)
- History size

## Configuration

### Environment Variables

```bash
# Bedrock Configuration
BEDROCK_MODEL=anthropic.claude-3-5-sonnet-20241022-v2:0
BEDROCK_REGION=us-east-1
BEDROCK_MAX_TOKENS=1000
BEDROCK_TEMPERATURE=0.7

# Optimization Configuration
OPTIMIZATION_TIMEOUT_MS=30000
OPTIMIZATION_RATE_LIMIT=10
OPTIMIZATION_CACHE_TTL_MS=3600000
OPTIMIZATION_MIN_LENGTH=10
OPTIMIZATION_MAX_LENGTH=2000

# Feature Flags
FEATURE_INSTRUCTION_OPTIMIZER_ENABLED=true
```

### Bedrock Prompt Template

```
You are an expert at writing clear, effective test instructions for automated testing.

Analyze the following test instruction and improve it for clarity, specificity, and effectiveness:

<instruction>
{USER_INSTRUCTION}
</instruction>

Provide:
1. An optimized version of the instruction
2. A list of specific improvements made

Format your response as JSON:
{
  "optimized": "the improved instruction text",
  "suggestions": ["improvement 1", "improvement 2", ...]
}

Guidelines:
- Be specific and actionable
- Use clear, simple language
- Include expected outcomes when relevant
- Remove ambiguity
- Keep the core intent intact
```

## Deployment Strategy

### Phase 1: Backend Deployment
1. Deploy Lambda function for optimization endpoint
2. Configure Bedrock permissions
3. Test endpoint with Postman/curl

### Phase 2: Frontend Deployment
1. Deploy feature flag disabled
2. Enable for internal testing (10% of users)
3. Monitor metrics and errors
4. Gather feedback

### Phase 3: General Availability
1. Enable feature flag for all users
2. Monitor costs and usage
3. Iterate based on feedback

## Future Enhancements

1. **Batch Optimization**: Optimize multiple instructions at once
2. **Custom Prompts**: Allow users to customize optimization style
3. **History Management**: View and revert past optimizations
4. **A/B Testing**: Compare original vs optimized instruction effectiveness
5. **Multi-language Support**: Optimize instructions in different languages
