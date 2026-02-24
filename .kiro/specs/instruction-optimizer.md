# Instruction Optimizer - Kiro IDE Feature Spec

**Version**: 1.0  
**Date**: 2025-12-09  
**Status**: Draft

---

## Overview

Add AI-powered instruction optimization to Kiro IDE's test creation workflow, allowing users to improve natural language test instructions using Amazon Bedrock.

---

## Architecture

### Component Structure

```
src/features/instruction-optimizer/
├── components/
│   ├── OptimizeButton.tsx          # Integrated into shared form
│   ├── OptimizationModal.tsx
│   └── ComparisonView.tsx
├── hooks/
│   ├── useOptimizeInstruction.ts
│   └── useOptimizationHistory.ts
├── services/
│   ├── optimizationApi.ts
│   └── bedrockClient.ts
├── store/
│   └── optimizationSlice.ts
└── types/
    └── optimization.types.ts

# Modifications to existing shared form:
src/components/shared/
├── Form.tsx                         # Add optimization support
└── FormField.tsx                    # Render OptimizeButton conditionally
```

---

## Shared Form Modifications

### Form.tsx Changes

```typescript
// Add optimization provider to form context
import { OptimizationProvider } from '@/features/instruction-optimizer';

export function Form({ fields, onSubmit, ...props }) {
  return (
    <OptimizationProvider>
      <form onSubmit={onSubmit}>
        {fields.map(field => (
          <FormField key={field.name} config={field} />
        ))}
      </form>
    </OptimizationProvider>
  );
}
```

### FormField.tsx Changes

```typescript
import { OptimizeButton } from '@/features/instruction-optimizer';

export function FormField({ config }) {
  const { setValue, watch } = useFormContext();
  const currentValue = watch(config.name);

  return (
    <div className="form-field">
      <label>{config.label}</label>
      <div className="field-input-wrapper">
        {/* Render field input based on config.type */}
        <textarea {...fieldProps} />
        
        {/* AI button only for optimizable fields */}
        {config.optimizable && (
          <OptimizeButton
            fieldName={config.name}
            currentValue={currentValue}
            context={config.optimizationContext}
            onAccepted={(value) => setValue(config.name, value)}
          />
        )}
      </div>
    </div>
  );
}
```

**Layout**:
```
┌─────────────────────────────────────┐
│ Instruction                         │
├─────────────────────────────────────┤
│                                 [AI]│
│  [textarea input field]             │
│                                     │
│                                     │
└─────────────────────────────────────┘
```

AI button positioned absolutely on right side of textarea.

---

## Data Models

### TypeScript Interfaces

```typescript
// Shared form field configuration extension
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
  };
}

interface OptimizationState {
  isOptimizing: boolean;
  result: OptimizationResponse | null;
  error: string | null;
  history: OptimizationHistory[];
}
```

---

## Integration with Shared Form

### Shared Form Extension

The optimizer integrates into the existing shared form component. Only instruction fields get the AI optimization button.

**Form Field Configuration**:
```typescript
interface FormFieldConfig {
  name: string;
  type: 'text' | 'textarea' | 'select' | ...;
  label: string;
  // New: optimization support
  optimizable?: boolean;
  optimizationContext?: {
    useCaseId: string;
    stepId: string;
  };
}
```

**Usage in Step Form**:
```typescript
const stepFormFields: FormFieldConfig[] = [
  {
    name: 'instruction',
    type: 'textarea',
    label: 'Instruction',
    optimizable: true,  // ← Only instruction fields
    optimizationContext: {
      useCaseId: currentUseCaseId,
      stepId: currentStepId,
    },
  },
  {
    name: 'expectedOutcome',
    type: 'textarea',
    label: 'Expected Outcome',
    // No optimizable flag - renders as normal textarea
  },
];
```

---

## UI Components

### 1. AI Optimize Button (Integrated into Shared Form)

**Location**: Next to instruction textarea field

**Position**: Right side of the textarea, vertically centered

**Visual**: AI icon button (no text label)

**Props** (internal to shared form):
```typescript
interface OptimizeButtonProps {
  fieldName: string;
  currentValue: string;
  context: OptimizationContext;
  onOptimized: (value: string) => void;
}
```

**States**:
- Default: AI icon (static)
- Loading: AI icon with spinner overlay
- Disabled: AI icon grayed out (when field is empty or < 10 chars)

**Behavior**:
- Click triggers optimization API call
- Opens OptimizationModal on success
- Shows error toast on failure
- Does NOT auto-apply - user must explicitly accept

---

### 2. OptimizationModal

**Layout**: Modal dialog (800px width)

**Sections**:
- Header: "Optimized Instruction"
- Body: Side-by-side comparison (ComparisonView)
- Footer: Action buttons

**Actions** (User must explicitly choose):
```typescript
- "Accept" → Replace instruction with optimized version, close modal
- "Reject" → Close modal, keep original instruction
```

**No auto-apply**: Modal requires explicit user action. Clicking outside or ESC key = Reject.

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

---

### 3. ComparisonView

**Layout**: Two-column grid

```
┌─────────────────┬─────────────────┐
│ Original        │ Optimized       │
├─────────────────┼─────────────────┤
│ [original text] │ [optimized text]│
│                 │                 │
│                 │ Suggestions:    │
│                 │ • [suggestion]  │
│                 │ • [suggestion]  │
└─────────────────┴─────────────────┘
```

**Features**:
- Diff highlighting (removed text in red, added text in green)
- Suggestions list below optimized text
- Character count for both versions

---

## Example Usage

### Step Form with Optimization

```typescript
// StepForm.tsx
import { Form } from '@/components/shared/Form';

export function StepForm({ useCaseId, stepId }) {
  const fields: FormFieldConfig[] = [
    {
      name: 'name',
      type: 'text',
      label: 'Step Name',
    },
    {
      name: 'instruction',
      type: 'textarea',
      label: 'Instruction',
      optimizable: true,
      optimizationContext: {
        useCaseId,
        stepId,
      },
    },
    {
      name: 'expectedOutcome',
      type: 'textarea',
      label: 'Expected Outcome',
    },
  ];

  return <Form fields={fields} onSubmit={handleSubmit} />;
}
```

### Other Forms (No Optimization)

```typescript
// LoginForm.tsx - No changes needed
const fields: FormFieldConfig[] = [
  { name: 'email', type: 'text', label: 'Email' },
  { name: 'password', type: 'password', label: 'Password' },
];

return <Form fields={fields} onSubmit={handleLogin} />;
```

---

## API Integration

### Service Layer

**File**: `services/optimizationApi.ts`

```typescript
export async function optimizeInstruction(
  useCaseId: string,
  stepId: string,
  instruction: string
): Promise<OptimizationResponse> {
  const response = await fetch(
    `/api/usecase/${useCaseId}/steps/${stepId}/optimize`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instruction }),
    }
  );

  if (!response.ok) {
    throw new OptimizationError(response.status, await response.text());
  }

  return response.json();
}
```

**Error Handling**:
```typescript
class OptimizationError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// Error messages by status code
const ERROR_MESSAGES = {
  400: 'Invalid instruction. Please provide clear text.',
  429: 'Too many requests. Please wait a moment.',
  500: 'Optimization service unavailable. Try again later.',
};
```

---

## State Management

### Hook: useOptimizeInstruction

```typescript
export function useOptimizeInstruction() {
  const [state, setState] = useState<OptimizationState>({
    isOptimizing: false,
    result: null,
    error: null,
  });

  const optimize = async (
    useCaseId: string,
    stepId: string,
    instruction: string
  ) => {
    setState({ isOptimizing: true, result: null, error: null });
    
    try {
      const result = await optimizeInstruction(useCaseId, stepId, instruction);
      setState({ isOptimizing: false, result, error: null });
      return result;
    } catch (error) {
      const message = error instanceof OptimizationError
        ? ERROR_MESSAGES[error.status] || error.message
        : 'An unexpected error occurred';
      setState({ isOptimizing: false, result: null, error: message });
      throw error;
    }
  };

  return { ...state, optimize };
}
```

---

## Rate Limiting

### Client-Side Throttling

```typescript
// utils/rateLimiter.ts
class RateLimiter {
  private requests: number[] = [];
  private limit = 10; // requests per minute
  private window = 60000; // 1 minute in ms

  canMakeRequest(): boolean {
    const now = Date.now();
    this.requests = this.requests.filter(time => now - time < this.window);
    return this.requests.length < this.limit;
  }

  recordRequest(): void {
    this.requests.push(Date.now());
  }
}

export const optimizationRateLimiter = new RateLimiter();
```

**Usage in Hook**:
```typescript
const optimize = async (...args) => {
  if (!optimizationRateLimiter.canMakeRequest()) {
    throw new Error('Rate limit exceeded. Please wait before optimizing again.');
  }
  
  optimizationRateLimiter.recordRequest();
  // ... rest of optimization logic
};
```

---

## Caching Strategy

### Cache Implementation

```typescript
// utils/optimizationCache.ts
interface CacheEntry {
  result: OptimizationResponse;
  timestamp: number;
}

class OptimizationCache {
  private cache = new Map<string, CacheEntry>();
  private ttl = 3600000; // 1 hour

  get(instruction: string): OptimizationResponse | null {
    const key = this.hash(instruction);
    const entry = this.cache.get(key);
    
    if (!entry) return null;
    if (Date.now() - entry.timestamp > this.ttl) {
      this.cache.delete(key);
      return null;
    }
    
    return entry.result;
  }

  set(instruction: string, result: OptimizationResponse): void {
    const key = this.hash(instruction);
    this.cache.set(key, { result, timestamp: Date.now() });
  }

  private hash(text: string): string {
    return btoa(text.trim().toLowerCase());
  }
}

export const optimizationCache = new OptimizationCache();
```

---

## Security Considerations

### Input Sanitization

```typescript
function sanitizeInstruction(instruction: string): string {
  // Remove potential PII patterns
  let sanitized = instruction
    .replace(/\b[\w\.-]+@[\w\.-]+\.\w+\b/g, '[EMAIL]')
    .replace(/\b\d{3}[-.]?\d{3}[-.]?\d{4}\b/g, '[PHONE]')
    .replace(/\b\d{3}-\d{2}-\d{4}\b/g, '[SSN]');
  
  // Limit length
  if (sanitized.length > 2000) {
    sanitized = sanitized.substring(0, 2000);
  }
  
  return sanitized.trim();
}
```

**Apply Before API Call**:
```typescript
const optimize = async (useCaseId, stepId, instruction) => {
  const sanitized = sanitizeInstruction(instruction);
  // ... proceed with API call
};
```

---

## User Flow

### Happy Path

1. User writes instruction in textarea field
2. User clicks AI icon button next to textarea
3. AI button shows loading state (spinner overlay)
4. Modal opens with side-by-side comparison
5. User reviews optimized version and suggestions
6. User clicks "Accept" button
7. Instruction field updates with optimized text
8. Modal closes
9. Optimization saved to history

### Rejection Path

1. User clicks AI icon button
2. Modal opens with optimization
3. User reviews and decides not to use it
4. User clicks "Reject" (or ESC key, or clicks outside modal)
5. Modal closes
6. Original instruction remains unchanged
7. Rejection tracked in analytics (not saved to history)

### Error Paths

**Empty/Short Instruction**:
- AI button disabled (grayed out)
- Tooltip on hover: "Enter at least 10 characters to optimize"

**Rate Limit Hit**:
- Show error toast: "Too many requests. Please wait a moment."
- AI button disabled for 60 seconds

**API Error**:
- Show error toast with user-friendly message
- AI button returns to default state
- User can retry

**Timeout (30s)**:
- Show error toast: "Optimization took too long. Please try again."
- AI button returns to default state

---

## Testing Strategy

### Unit Tests

```typescript
// OptimizeButton.test.tsx
describe('OptimizeButton', () => {
  it('disables when instruction is empty');
  it('shows loading state during optimization');
  it('calls onOptimize with result on success');
  it('shows error toast on failure');
});

// useOptimizeInstruction.test.ts
describe('useOptimizeInstruction', () => {
  it('returns optimized instruction on success');
  it('handles rate limiting');
  it('uses cached results for identical instructions');
  it('sanitizes input before sending');
});
```

### Integration Tests

```typescript
describe('Instruction Optimization Flow', () => {
  it('optimizes instruction end-to-end');
  it('applies optimized instruction to form');
  it('saves optimization to history');
  it('handles network errors gracefully');
});
```

---

## Performance Metrics

### Track These Metrics

- Optimization request count per user/day
- Average response time
- Cache hit rate
- Error rate by type (400, 429, 500, timeout)
- Acceptance rate (% of optimizations applied)
- Token usage per request

### Implementation

```typescript
interface OptimizationMetrics {
  requestCount: number;
  avgResponseTime: number;
  cacheHitRate: number;
  errorRate: Record<number, number>;
  acceptanceRate: number;
  tokenUsage: number;
}

function trackOptimization(event: 'request' | 'success' | 'error' | 'apply', data?: any) {
  // Send to analytics service
  analytics.track('instruction_optimization', { event, ...data });
}
```

---

## Configuration

### Environment Variables

```bash
BEDROCK_MODEL=anthropic.claude-3-5-sonnet-20241022-v2:0
BEDROCK_REGION=us-east-1
OPTIMIZATION_TIMEOUT_MS=30000
OPTIMIZATION_RATE_LIMIT=10
OPTIMIZATION_CACHE_TTL_MS=3600000
```

### Feature Flag

```typescript
const FEATURE_FLAGS = {
  instructionOptimizer: {
    enabled: true,
    maxInstructionLength: 2000,
    minInstructionLength: 10,
  },
};
```

---

## Rollout Plan

### Phase 1: Internal Testing (Week 1)
- Deploy to staging environment
- Test with internal team
- Gather feedback on UX and accuracy

### Phase 2: Beta (Week 2-3)
- Enable for 10% of users
- Monitor metrics and error rates
- Iterate on prompts based on feedback

### Phase 3: General Availability (Week 4)
- Enable for all users
- Monitor cost and usage
- Prepare for Feature 2 (Failed Execution Analyzer)

---

## Open Questions

1. Should we show token usage/cost to users?
2. Do we need undo functionality after applying optimization?
3. Should we allow users to provide feedback on optimization quality?
4. Do we need admin controls for rate limits and quotas?
5. Should optimization history be exportable?

---

## Dependencies

- Amazon Bedrock SDK
- AWS credentials configured in Kiro IDE
- Backend API endpoints deployed
- UI component library (for modal, buttons, etc.)

---

## Acceptance Criteria

- [ ] AI icon button appears next to instruction textarea fields only
- [ ] AI button is disabled when instruction is empty or < 10 characters
- [ ] User can click AI button to trigger optimization
- [ ] System sends instruction to Bedrock and receives optimized version
- [ ] Modal opens showing side-by-side comparison
- [ ] User must explicitly click "Accept" to apply optimization
- [ ] User can click "Reject" (or ESC/outside click) to dismiss without changes
- [ ] Accepted optimizations update the instruction field
- [ ] Rejected optimizations leave original text unchanged
- [ ] System tracks optimization history (accepted only)
- [ ] Rate limiting prevents abuse
- [ ] Error states are handled gracefully
- [ ] Non-instruction fields render as normal inputs without AI button

---

## Success Criteria

- [ ] 80%+ of optimizations complete within 10 seconds
- [ ] <5% error rate
- [ ] 50%+ acceptance rate (users apply optimizations)
- [ ] Cache hit rate >30%
- [ ] Zero PII leaks to Bedrock
- [ ] Rate limiting prevents abuse
- [ ] User satisfaction score >4/5
