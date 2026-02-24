# Implementation Plan

- [ ] 1. Set up project structure and type definitions
  - Create feature directory structure: `frontend/src/features/instruction-optimizer/`
  - Create subdirectories: components, hooks, services, utils, types
  - Define TypeScript interfaces in `types/optimization.types.ts`
  - Export public API from `index.ts`
  - _Requirements: 1.1, 4.1, 4.2_

- [ ] 2. Implement input sanitization utility
  - Create `utils/sanitizer.ts` with sanitizeInstruction function
  - Implement email pattern replacement with [EMAIL]
  - Implement phone number pattern replacement with [PHONE]
  - Implement SSN pattern replacement with [SSN]
  - Implement length truncation to 2000 characters
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 3. Implement client-side rate limiter
  - Create `utils/rateLimiter.ts` with RateLimiter class
  - Implement request tracking with timestamps
  - Implement canMakeRequest method (10 requests per minute limit)
  - Implement recordRequest method
  - Implement time window cleanup logic
  - _Requirements: 3.1, 3.2_

- [ ] 4. Implement optimization cache
  - Create `utils/cache.ts` with OptimizationCache class
  - Implement get method with TTL check (1 hour)
  - Implement set method with timestamp
  - Implement hash function for cache keys
  - Implement automatic expiration cleanup
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [ ] 5. Implement optimization API service
  - Create `services/optimizationApi.ts` with optimizeInstruction function
  - Implement POST request to `/api/usecase/{id}/steps/{id}/optimize`
  - Implement error handling with OptimizationError class
  - Implement timeout handling (30 seconds)
  - Map HTTP status codes to user-friendly error messages
  - _Requirements: 1.3, 8.2, 8.3, 8.4_

- [ ] 6. Implement useOptimizeInstruction hook
  - Create `hooks/useOptimizeInstruction.ts`
  - Implement state management (isOptimizing, result, error)
  - Integrate rate limiter check before API call
  - Integrate cache lookup before API call
  - Integrate sanitizer before API call
  - Store result in cache after success
  - _Requirements: 1.3, 3.1, 3.2, 5.2, 7.1, 7.2, 7.3, 7.4_

- [ ] 7. Implement ComparisonView component
  - Create `components/ComparisonView.tsx`
  - Implement two-column grid layout
  - Implement diff highlighting (red for removed, green for added)
  - Display character counts for both versions
  - Display suggestions list below optimized text
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [ ] 8. Implement OptimizationModal component
  - Create `components/OptimizationModal.tsx`
  - Implement modal dialog with 800px width
  - Render ComparisonView in modal body
  - Implement Accept and Reject buttons
  - Handle ESC key press to trigger onReject
  - Handle outside click to trigger onReject
  - _Requirements: 1.4, 1.5, 2.5_

- [ ] 9. Implement OptimizeButton component
  - Create `components/OptimizeButton.tsx`
  - Render AI icon button
  - Implement disabled state when text length < 10 characters
  - Implement loading state with spinner overlay
  - Implement tooltip for disabled state
  - Call useOptimizeInstruction hook on click
  - Open OptimizationModal on success
  - Display error toast on failure
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 8.1, 8.5_

- [ ] 10. Implement notification context
  - Create `context/NotificationContext.tsx`
  - Provide notification methods to child components
  - Implement toast notifications with auto-dismiss
  - _Requirements: 3.3, 8.2, 8.3, 8.4_

- [ ] 11. Integrate OptimizeButton into StepForm
  - Modify `components/wizard/StepForm.tsx`
  - Add OptimizeButton next to instruction textarea
  - Pass useCaseId and stepId as context
  - Wire up onAccepted callback to update instruction value
  - Wrap with NotificationProvider
  - _Requirements: 1.1, 4.1, 4.3_

- [ ] 12. Create Lambda handler for optimization endpoint
  - Create `lambda/cmd/optimize_instruction/main.go`
  - Implement handler function
  - Validate authentication from JWT token
  - Validate input (length, content)
  - Extract useCaseId and stepId from path parameters
  - Parse request body for instruction text
  - _Requirements: 1.3_

- [ ] 13. Implement Bedrock client integration
  - Create Bedrock client in Lambda handler
  - Configure model: anthropic.claude-3-5-sonnet-20241022-v2:0
  - Construct prompt with instruction text
  - Set parameters: max_tokens=1000, temperature=0.7
  - Implement timeout handling (25 seconds)
  - Implement retry logic (3 attempts with exponential backoff)
  - Parse JSON response from Bedrock
  - _Requirements: 1.3, 1.4_

- [ ] 14. Implement Lambda error handling
  - Return 400 for invalid input
  - Return 429 for rate limit exceeded
  - Return 500 for Bedrock errors
  - Return 504 for timeout
  - Log all errors to standard output
  - _Requirements: 8.2, 8.3, 8.4_

- [ ] 15. Add API Gateway endpoint
  - Create POST endpoint: `/api/usecase/{useCaseId}/steps/{stepId}/optimize`
  - Configure CORS headers
  - Set timeout to 30 seconds
  - Configure rate limiting (20 requests per minute per user)
  - Wire up to Lambda handler
  - _Requirements: 1.3, 3.2_

- [ ] 16. Configure Bedrock permissions
  - Add IAM policy for Lambda to invoke Bedrock
  - Specify model ARN in policy
  - Configure region: us-east-1
  - Test permissions with sample request
  - _Requirements: 1.3_

- [ ] 17. Add environment configuration
  - Add environment variables to Lambda
  - Add feature flag: FEATURE_INSTRUCTION_OPTIMIZER_ENABLED
  - Add Bedrock configuration variables
  - Document all variables in README
  - _Requirements: 1.1_

- [ ] 18. Add CSS styling for optimization components
  - Style OptimizeButton (AI icon, positioning)
  - Style OptimizationModal (layout, spacing)
  - Style ComparisonView (grid, diff colors)
  - Style loading states
  - Style error states
  - Ensure responsive design
  - _Requirements: 1.1, 2.1, 2.2, 2.3, 4.4_

- [ ] 19. Create CDK optimization stack
  - Create `lib/optimization-stack.ts`
  - Define Lambda function resource
  - Define API Gateway integration
  - Configure IAM roles and policies
  - Add to main CDK app
  - _Requirements: 1.3_

- [ ] 20. Create documentation
  - Document feature in README
  - Document API endpoint
  - Document configuration options
  - Add troubleshooting steps
  - _Requirements: 1.1_

- [ ] 21. Final checkpoint - Manual testing
  - Test optimization flow end-to-end
  - Test error handling
  - Test rate limiting
  - Test caching
  - Ask user if questions arise
