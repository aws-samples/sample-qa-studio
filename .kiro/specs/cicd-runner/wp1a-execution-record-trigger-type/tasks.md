# Work Package 1a: Execution Record & Trigger Type - Tasks

## Feature Information
- **Epic**: CI/CD Test Runner
- **Work Package**: WP1a - Execution Record & Trigger Type
- **Estimated Duration**: 3 days
- **Status**: Ready for Implementation

---

## Task List

### 1. Update execute_usecase Lambda for ci_runner Trigger

- [x] 1.1 Add `ci_runner` to valid trigger types list
  - Update trigger type validation in `execute_usecase.py`
  - Add `ci_runner` to the list of valid values
  - Update docstring to document new trigger type

- [x] 1.2 Add conditional logic to skip ECS task creation for ci_runner
  - Add `elif trigger_type == 'ci_runner':` branch
  - Skip ECS task creation logic
  - Return appropriate response with execution_id
  - Log ci_runner execution creation

- [x] 1.3 Update response format for ci_runner trigger
  - Return `{"status": "execution created", "usecaseId": "...", "executionId": "..."}`
  - Ensure backward compatibility for other trigger types
  - Test response format matches specification

### 2. Create Step Status Update Endpoint

- [x] 2.1 Create new Lambda function `update_execution_step_status.py`
  - Create file in `lambdas/endpoints/`
  - Implement handler function
  - Add authentication check using `allow_m2m_token()`
  - Parse path parameters (usecase_id, execution_id, step_id)
  - Parse request body (status, started_at, completed_at, error_message)

- [x] 2.2 Implement status validation
  - Validate status is one of: pending, running, completed, failed, skipped
  - Return 400 error for invalid status values
  - Validate required fields are present

- [x] 2.3 Implement execution and step existence checks
  - Query DynamoDB to verify execution exists
  - Query DynamoDB to verify step exists
  - Return 404 if execution or step not found
  - Add appropriate error messages

- [x] 2.4 Implement DynamoDB update logic
  - Build dynamic UpdateExpression based on provided fields
  - Update step status in DynamoDB
  - Update started_at if provided
  - Update completed_at if provided
  - Update error_message if provided
  - Handle DynamoDB update errors

- [x] 2.5 Return success response
  - Return `{"success": true, "step_id": "...", "status": "..."}`
  - Log successful update
  - Include appropriate status code (200)

### 3. Add API Gateway Configuration

- [x] 3.1 Add step status update endpoint to API Gateway
  - Add route: `PATCH /usecase/{id}/executions/{executionId}/steps/{stepId}/status`
  - Configure Lambda integration
  - Add Cognito authorizer
  - Configure CORS if needed

- [x] 3.2 Configure OAuth scope validation
  - Require `api/execution.write` scope
  - Test scope validation works
  - Verify 403 returned for insufficient permissions

### 4. Write Unit Tests

- [x] 4.1 Test execute_usecase with ci_runner trigger
  - Test execution record created with trigger_type='ci_runner'
  - Test no ECS task spawned
  - Test correct response returned
  - Test steps, hooks, variables, headers copied correctly

- [x] 4.2 Test execute_usecase backward compatibility
  - Test OnDemand trigger still sends to SQS
  - Test Scheduled trigger still spawns ECS task
  - Test OnDemandHeadless trigger still spawns ECS task
  - Test default trigger_type is 'OnDemand'

- [x] 4.3 Test execute_usecase validation
  - Test invalid trigger_type returns 400
  - Test error message is clear
  - Test authentication required

- [x] 4.4 Test update_execution_step_status success cases
  - Test valid status update
  - Test status update with started_at
  - Test status update with completed_at
  - Test status update with error_message
  - Test all status values (pending, running, completed, failed, skipped)

- [x] 4.5 Test update_execution_step_status error cases
  - Test invalid status returns 400
  - Test non-existent execution returns 404
  - Test non-existent step returns 404
  - Test missing required fields returns 400
  - Test insufficient permissions returns 403

- [x] 4.6 Achieve 70% test coverage
  - Run coverage report
  - Add additional tests if needed
  - Verify all critical paths tested

### 5. Update CDK Infrastructure

- [x] 5.1 Add update_execution_step_status Lambda to CDK stack
  - Define Lambda function in CDK
  - Configure environment variables
  - Set appropriate timeout and memory
  - Grant DynamoDB permissions

- [x] 5.2 Add API Gateway route for step status update
  - Add PATCH route to API Gateway
  - Configure Lambda integration
  - Add Cognito authorizer
  - Configure request/response models

- [x] 5.3 Update IAM permissions
  - Grant Lambda permission to update DynamoDB items
  - Grant Lambda permission to query DynamoDB
  - Verify least privilege principle

### 6. Documentation

- [x] 6.1 Update API documentation
  - Document ci_runner trigger type
  - Document step status update endpoint
  - Add request/response examples
  - Document error codes

- [x] 6.2 Update Lambda function docstrings
  - Update execute_usecase docstring
  - Add docstring to update_execution_step_status
  - Document parameters and return values

- [x] 6.3 Add inline code comments
  - Comment ci_runner logic in execute_usecase
  - Comment step status update logic
  - Explain validation logic

### 7. Testing & Validation

- [ ] 7.1 Manual testing in development environment
  - Deploy to dev environment
  - Test ci_runner execution creation
  - Test step status updates
  - Test error scenarios
  - Verify CloudWatch logs

- [ ] 7.2 Verify backward compatibility
  - Test existing OnDemand executions
  - Test existing Scheduled executions
  - Test existing OnDemandHeadless executions
  - Verify no regressions

- [ ] 7.3 Performance testing
  - Test execution creation latency
  - Test step status update latency
  - Verify no performance degradation
  - Check DynamoDB read/write capacity

- [ ] 7.4 Security testing
  - Test OAuth scope validation
  - Test authentication required
  - Test authorization for step updates
  - Verify error messages don't leak sensitive data

### 8. Deployment

- [ ] 8.1 Deploy to development environment
  - Run CDK deploy
  - Verify Lambda functions deployed
  - Verify API Gateway routes created
  - Check CloudWatch logs for errors

- [ ] 8.2 Run smoke tests
  - Create test execution with ci_runner trigger
  - Update test step status
  - Verify responses correct
  - Check DynamoDB records

- [ ] 8.3 Deploy to production
  - Review deployment plan
  - Deploy during maintenance window
  - Monitor CloudWatch metrics
  - Verify no errors in logs

- [ ] 8.4 Post-deployment validation
  - Test ci_runner trigger in production
  - Test step status updates in production
  - Verify existing executions still work
  - Monitor for 24 hours

---

## Task Dependencies

```
1.1 → 1.2 → 1.3
2.1 → 2.2 → 2.3 → 2.4 → 2.5
3.1 → 3.2
4.1, 4.2, 4.3 (parallel)
4.4, 4.5 (parallel)
4.6 (after all unit tests)
5.1 → 5.2 → 5.3
6.1, 6.2, 6.3 (parallel)
7.1 → 7.2 → 7.3 → 7.4
8.1 → 8.2 → 8.3 → 8.4
```

---

## Estimated Time Breakdown

- Task 1: Update execute_usecase Lambda - 4 hours
- Task 2: Create step status update endpoint - 6 hours
- Task 3: API Gateway configuration - 2 hours
- Task 4: Unit tests - 6 hours
- Task 5: CDK infrastructure - 3 hours
- Task 6: Documentation - 2 hours
- Task 7: Testing & validation - 4 hours
- Task 8: Deployment - 3 hours

**Total**: ~30 hours (~4 days with buffer)

**Note**: Integration tests will be added in a later workpackage

---

## Success Criteria

All tasks completed and:
- [ ] ci_runner trigger type works correctly
- [ ] No ECS task spawned for ci_runner executions
- [ ] Step status update endpoint functional
- [ ] All unit tests pass (≥70% coverage)
- [ ] No regressions in existing functionality
- [ ] Documentation updated
- [ ] Successfully deployed to production
- [ ] No errors in production logs after 24 hours

---

## Notes

- Prioritize backward compatibility - existing executions must continue to work
- Test thoroughly with OAuth M2M tokens (CI/CD runner authentication)
- Monitor DynamoDB capacity during testing
- Keep changes minimal and focused on WP1a scope
- Coordinate with WP1b team on API contract
- Integration tests deferred to later workpackage
