# Implementation Plan

- [x] 1. Update Worker Stack to pass VPC configuration to Lambda functions
  - Add VPC_PRIVATE_SUBNET_IDS environment variable to executeUsecaseLambda
  - Add BROWSER_SECURITY_GROUP_ID environment variable to executeUsecaseLambda
  - Add VPC_PRIVATE_SUBNET_IDS environment variable to startWizardLambda
  - Add BROWSER_SECURITY_GROUP_ID environment variable to startWizardLambda
  - Ensure agentCoreExecutionRole has CloudWatch Logs permissions
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 4.5_

- [x] 2. Update Execute Usecase Lambda to propagate VPC configuration to ECS tasks
  - Read VPC_PRIVATE_SUBNET_IDS from environment variables
  - Read BROWSER_SECURITY_GROUP_ID from environment variables
  - Add VPC_PRIVATE_SUBNET_IDS to ECS task environment overrides
  - Add BROWSER_SECURITY_GROUP_ID to ECS task environment overrides
  - _Requirements: 2.1, 2.2, 5.4, 6.4_

- [x] 3. Update Start Wizard Lambda to propagate VPC configuration to ECS tasks
  - Read VPC_PRIVATE_SUBNET_IDS from environment variables
  - Read BROWSER_SECURITY_GROUP_ID from environment variables
  - Add VPC_PRIVATE_SUBNET_IDS to ECS task environment overrides
  - Add BROWSER_SECURITY_GROUP_ID to ECS task environment overrides
  - _Requirements: 6.1, 6.3, 6.4_

- [x] 4. Update browser.py to support VPC network configuration
- [x] 4.1 Modify create_browser function signature
  - Add vpc_subnet_ids parameter (optional list of strings)
  - Add security_group_ids parameter (optional list of strings)
  - _Requirements: 1.1, 2.3_

- [x] 4.2 Implement VPC network configuration logic
  - Check if vpc_subnet_ids and security_group_ids are provided
  - Set networkMode to "VPC" when VPC config is provided
  - Add networkModeConfig with subnets and securityGroups
  - Fallback to networkMode "PUBLIC" when VPC config is missing
  - _Requirements: 1.1, 2.3, 2.4, 9.1, 9.4_

- [x] 4.3 Add error logging for VPC configuration
  - Log warning when VPC config is incomplete
  - Log error when browser creation fails with VPC details
  - _Requirements: 7.1, 7.2, 7.4_

- [x] 5. Update worker.py to read and pass VPC configuration
- [x] 5.1 Read VPC configuration from environment variables
  - Read VPC_PRIVATE_SUBNET_IDS environment variable
  - Read BROWSER_SECURITY_GROUP_ID environment variable
  - Parse comma-separated subnet IDs into list
  - Create security group IDs list
  - _Requirements: 5.1, 5.2, 5.3_

- [x] 5.2 Pass VPC configuration to create_browser
  - Pass vpc_subnet_ids parameter to create_browser
  - Pass security_group_ids parameter to create_browser
  - Handle None values for backward compatibility
  - _Requirements: 5.5, 9.2, 9.3_

- [x] 6. Update wizard_worker.py to read and pass VPC configuration
- [x] 6.1 Read VPC configuration from environment variables
  - Read VPC_PRIVATE_SUBNET_IDS environment variable
  - Read BROWSER_SECURITY_GROUP_ID environment variable
  - Parse comma-separated subnet IDs into list
  - Create security group IDs list
  - _Requirements: 6.1, 6.2_

- [x] 6.2 Pass VPC configuration to create_browser in wizard mode
  - Pass vpc_subnet_ids parameter to create_browser
  - Pass security_group_ids parameter to create_browser
  - Ensure consistency with regular execution mode
  - _Requirements: 6.1, 6.2, 6.5_

- [x] 7. Checkpoint - Verify all changes compile and basic functionality works
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Test VPC browser creation end-to-end
  - Deploy stack with VPC configuration
  - Create test usecase execution
  - Verify browser is created in VPC mode
  - Verify browser can access internet
  - Verify recording is saved to S3
  - _Requirements: 1.1, 1.4, 1.5_

- [x] 9. Test backward compatibility
  - Deploy stack without VPC configuration
  - Create test usecase execution
  - Verify browser is created in PUBLIC mode
  - Verify execution completes successfully
  - _Requirements: 9.1, 9.2, 9.4_

- [ ] 10. Test wizard mode with VPC
  - Start wizard session with VPC configuration
  - Verify browser is created in VPC mode
  - Execute wizard steps
  - Verify browser functionality
  - _Requirements: 6.1, 6.2, 6.3_

- [ ] 11. Test error scenarios
  - Test with invalid subnet IDs
  - Test with invalid security group ID
  - Test with missing execution role
  - Verify error messages are clear
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 12. Final Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
