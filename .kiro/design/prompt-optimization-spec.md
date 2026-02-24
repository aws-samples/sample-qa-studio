# Prompt Optimization Feature Specification

## Overview
Add AI-powered prompt optimization to help users create better workflow step instructions using Amazon Bedrock. This feature will provide real-time suggestions to improve instruction clarity, specificity, and effectiveness.

## User Story
As a workflow creator, I want to optimize my step instructions using AI so that my automation workflows are more reliable and easier to understand.

## Feature Location
- **Component**: `StepFormModal.tsx` (frontend/src/components/usecase/)
- **Trigger**: Button next to the Instruction textarea field
- **UI Pattern**: Side drawer (Cloudscape Drawer component)

## Functional Requirements

### 1. UI Components

#### 1.1 Optimize Button
- **Location**: Right side of the "Instruction" FormField label
- **Appearance**: Icon button with sparkle/wand icon
- **State**: 
  - Disabled when instruction field is empty
  - Loading state while processing
  - Enabled when instruction has content

#### 1.2 Optimization Drawer
- **Component**: Cloudscape Drawer
- **Position**: Right side of screen
- **Width**: 400-500px
- **Sections**:
  1. **Optimized Instructions** (1-5 suggestions)
  2. **Improvement Hints** (actionable recommendations)

### 2. Backend API

#### 2.1 New Lambda Function
- **Name**: `OptimizePromptFunction`
- **Runtime**: Go 1.22
- **Path**: `lambda/optimize-prompt/`
- **Endpoint**: `POST /api/optimize-prompt`

#### 2.2 Request Schema
```json
{
  "instruction": "string (required)",
  "stepType": "string (required)",
  "context": {
    "previousSteps": ["string"],
    "availableVariables": ["string"]
  }
}
```

#### 2.3 Response Schema
```json
{
  "optimizedInstructions": [
    {
      "text": "string",
      "reasoning": "string"
    }
  ],
  "hints": [
    {
      "category": "string",
      "suggestion": "string",
      "priority": "high|medium|low"
    }
  ]
}
```

### 3. Bedrock Integration

#### 3.1 Model Selection
- **Primary**: Claude 3.5 Sonnet (anthropic.claude-3-5-sonnet-20241022-v2:0)
- **Fallback**: Claude 3 Haiku for cost optimization

#### 3.2 Prompt Template
```
You are an expert at creating clear, actionable browser automation instructions.

Context:
- Step Type: {stepType}
- Current Instruction: {instruction}
- Previous Steps: {previousSteps}

Task: Optimize this instruction for browser automation. Provide:
1. 1-5 improved versions (ordered by quality)
2. Specific improvement hints

Focus on:
- Clarity and specificity
- Actionable language
- Proper element identification
- Error handling considerations

Return JSON format:
{
  "optimizedInstructions": [...],
  "hints": [...]
}
```

#### 3.3 Hint Categories
1. **Split Steps**: Suggest breaking complex instructions into multiple steps
2. **Be Specific**: Add specific element identifiers (button text, labels, etc.)
3. **Simplify**: Remove unnecessary complexity
4. **Add Context**: Include page context or expected state
5. **Error Handling**: Consider edge cases and error scenarios

### 4. Frontend Implementation

#### 4.1 New Hook: `usePromptOptimization`
```typescript
interface UsePromptOptimizationResult {
  optimize: (instruction: string, stepType: string) => Promise<void>;
  isOptimizing: boolean;
  optimizedInstructions: OptimizedInstruction[];
  hints: OptimizationHint[];
  error: string | null;
  clearResults: () => void;
}
```

#### 4.2 Drawer Component Structure
```typescript
<Drawer
  header="Optimize Instruction"
  loading={isOptimizing}
>
  <SpaceBetween size="l">
    {/* Optimized Instructions Section */}
    <Container header="Suggested Instructions">
      {optimizedInstructions.map((opt, idx) => (
        <Card
          key={idx}
          actions={
            <Button onClick={() => applyInstruction(opt.text)}>
              Apply
            </Button>
          }
        >
          <SpaceBetween size="xs">
            <Box variant="p">{opt.text}</Box>
            <Box variant="small" color="text-body-secondary">
              {opt.reasoning}
            </Box>
          </SpaceBetween>
        </Card>
      ))}
    </Container>

    {/* Hints Section */}
    <Container header="Improvement Hints">
      {hints.map((hint, idx) => (
        <Alert
          key={idx}
          type={hint.priority === 'high' ? 'warning' : 'info'}
          header={hint.category}
        >
          {hint.suggestion}
        </Alert>
      ))}
    </Container>
  </SpaceBetween>
</Drawer>
```

### 5. User Interaction Flow

1. User enters instruction in textarea
2. User clicks optimize button
3. Drawer opens with loading state
4. API call to Lambda → Bedrock
5. Results populate drawer:
   - Optimized instructions with "Apply" buttons
   - Improvement hints with categories
6. User can:
   - Apply any suggested instruction (replaces current text)
   - Read hints and manually adjust
   - Close drawer and keep original

## Technical Implementation

### File Structure
```
lambda/optimize-prompt/
├── main.go
├── handler.go
└── bedrock.go

frontend/src/
├── components/usecase/
│   ├── StepFormModal.tsx (modify)
│   └── PromptOptimizationDrawer.tsx (new)
├── hooks/
│   └── usePromptOptimization.ts (new)
└── utils/
    └── api.ts (add endpoint)
```

### Lambda Handler (Go)
```go
type OptimizePromptRequest struct {
    Instruction string                 `json:"instruction"`
    StepType    string                 `json:"stepType"`
    Context     map[string]interface{} `json:"context"`
}

type OptimizedInstruction struct {
    Text      string `json:"text"`
    Reasoning string `json:"reasoning"`
}

type OptimizationHint struct {
    Category   string `json:"category"`
    Suggestion string `json:"suggestion"`
    Priority   string `json:"priority"`
}

type OptimizePromptResponse struct {
    OptimizedInstructions []OptimizedInstruction `json:"optimizedInstructions"`
    Hints                 []OptimizationHint     `json:"hints"`
}
```

### API Gateway Integration
- **Method**: POST
- **Path**: `/optimize-prompt`
- **Auth**: Cognito User Pool
- **CORS**: Enabled
- **Timeout**: 30 seconds

### CDK Stack Updates
```typescript
// lib/nova-act-qa-studio-stack.ts

const optimizePromptFunction = new lambda.Function(this, 'OptimizePromptFunction', {
  runtime: lambda.Runtime.PROVIDED_AL2023,
  handler: 'bootstrap',
  code: lambda.Code.fromAsset('lambda/optimize-prompt'),
  timeout: Duration.seconds(30),
  environment: {
    BEDROCK_MODEL_ID: 'anthropic.claude-3-5-sonnet-20241022-v2:0',
    BEDROCK_REGION: this.region,
  },
});

// Grant Bedrock permissions
optimizePromptFunction.addToRolePolicy(new iam.PolicyStatement({
  actions: ['bedrock:InvokeModel'],
  resources: ['*'],
}));

// Add API Gateway route
api.root.addResource('optimize-prompt').addMethod('POST', 
  new apigateway.LambdaIntegration(optimizePromptFunction),
  {
    authorizer: cognitoAuthorizer,
  }
);
```

## Non-Functional Requirements

### Performance
- API response time: < 5 seconds (p95)
- Drawer open animation: < 300ms
- No blocking of main form interaction

### Security
- All API calls authenticated via Cognito
- No PII sent to Bedrock
- Rate limiting: 10 requests per minute per user

### Cost Optimization
- Cache common optimizations (optional future enhancement)
- Use Haiku model for simple instructions
- Implement request throttling

### Error Handling
- Network errors: Show retry button
- Bedrock errors: Fallback message with manual tips
- Timeout: Clear error message with suggestion to simplify
- Empty results: Provide generic improvement tips

## Testing Requirements

### Unit Tests
- Hook logic (usePromptOptimization)
- API request/response parsing
- Error handling scenarios

### Integration Tests
- Lambda function with mock Bedrock responses
- API Gateway endpoint authorization
- Frontend drawer interactions

### E2E Tests
- Complete optimization flow
- Apply instruction functionality
- Error state handling

## Future Enhancements

1. **Learning from History**: Analyze successful vs failed executions to improve suggestions
2. **Context-Aware**: Use previous step outcomes to inform suggestions
3. **Multi-Language**: Support instructions in multiple languages
4. **Batch Optimization**: Optimize all steps in a workflow at once
5. **A/B Testing**: Compare original vs optimized instruction success rates
6. **Custom Prompts**: Allow users to define optimization preferences

## Success Metrics

- Adoption rate: % of users who use optimization feature
- Application rate: % of optimized suggestions applied
- Workflow success rate: Compare workflows with/without optimization
- User satisfaction: In-app feedback on suggestions

## Dependencies

- AWS Bedrock access in deployment region
- Cloudscape Design System v3.x
- React 18+
- AWS SDK for JavaScript v3
- Go 1.22+ for Lambda

## Rollout Plan

### Phase 1: MVP (Week 1-2)
- Basic Lambda function with Bedrock integration
- Simple drawer UI with suggestions
- Apply functionality

### Phase 2: Enhancement (Week 3)
- Hint categories and prioritization
- Context-aware suggestions
- Error handling improvements

### Phase 3: Polish (Week 4)
- Performance optimization
- Analytics integration
- User feedback collection

## Open Questions

1. Should we store optimization history for analytics?
2. Do we need admin controls for feature toggle?
3. Should optimizations be versioned/tracked?
4. Rate limiting strategy per user vs per account?
