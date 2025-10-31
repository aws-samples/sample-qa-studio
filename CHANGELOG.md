# Changelog

All notable changes to this project will be documented in this file.

## [0.1.1-14] - 2025-10-31

### Features

- Decouple CDK stacks and implement release mechanism (7e66e45)

### Bug Fixes

- solve a permission error that prevents the events lambda from reading the artifacts bucket (411ac85)

### Chores

- release v0.1.1-13 (3650629)

### Other Changes

- Enable video playback for executed sessions (9c9f129)

All notable changes to this project will be documented in this file.

## [0.1.1-13] - 2025-10-31

### Features

- Decouple CDK stacks and implement release mechanism (7e66e45)

### Other Changes

- Enable video playback for executed sessions (9c9f129)

All notable changes to this project will be documented in this file.

## [0.1.1-12] - 2025-10-23

### Other Changes

- make api enpoint confgurable (074115a)
- add deployment of the api gateway (a58df0e)

All notable changes to this project will be documented in this file.

## [0.1.1-11] - 2025-10-23

### Other Changes

- deploy api gateway after changing routes (a7c954c)

All notable changes to this project will be documented in this file.

## [0.1.1-10] - 2025-10-22

### Chores

- release v0.1.1-9 (a99b960)

### Other Changes

- improve build process (6430d59)

All notable changes to this project will be documented in this file.

## [0.1.1-9] - 2025-10-22

### Other Changes

- improve build process (6430d59)

All notable changes to this project will be documented in this file.

## [0.1.1-9] - 2025-10-22

### Other Changes

- more fixes to deploy and build the frontend (cfc4ae4)

All notable changes to this project will be documented in this file.

## [0.1.1-8] - 2025-10-22

### Other Changes

- ensure synth can run (4455db0)

All notable changes to this project will be documented in this file.

## [0.1.1-7] - 2025-10-22

### Other Changes

- rework release creation (b95fc79)

All notable changes to this project will be documented in this file.

## [0.1.1-6] - 2025-10-22

### Other Changes

- update deployment proces (30a3a1e)

All notable changes to this project will be documented in this file.

## [0.1.1-5] - 2025-10-22

### Other Changes

- fixes release paths (256e2bf)

All notable changes to this project will be documented in this file.

## [0.1.1-4] - 2025-10-22

### Other Changes

- fix faulty import (dfac38e)

All notable changes to this project will be documented in this file.

## [0.1.1-3] - 2025-10-22

### Other Changes

- update release process (8c54f60)

All notable changes to this project will be documented in this file.

## [0.1.1-2] - 2025-10-22

### Documentation

- **readme**: add step for uploading Nova Act API Key Secret (f1c0830)
- **readme**: tweak post deployment steps (1de6ce3)
- **readme**: add step for uploading Nova Act API Key Secret (27f1d26)
- **readme**: tweak post deployment steps (f5e035b)

### Chores

- create sg for ecs tasks (de7ee2d)

### Other Changes

- fix frontend release path (c80fa1a)
- add initial release functionallity (5e274c9)
- implement a release process (337a609)
- cleanup CDK setup and deployment instructions (ffe75d5)
- split stacks (279018f)
- cleanup makefile sample (ccb82b3)
- Merge pull request #31 from aws-samples/29-add-header-to-requests (3c9d86c)
- Merge branch 'main' into 29-add-header-to-requests (fa0373d)
- Merge pull request #28 from aws-samples/26-updating-a-test-care-requires-tags-while-creating-does-not (ebce780)
- Merge pull request #27 from aws-samples/9-test-failure-notifications (4019591)
- Merge branch 'main' into 9-test-failure-notifications (1814591)
- Merge pull request #24 from aws-samples/23-manage-userpool (4e4c237)
- Merge branch 'main' into 23-manage-userpool (86705ab)
- Merge branch 'main' into 9-test-failure-notifications (f2aecbd)
- Merge pull request #12 from aws-samples/8-embed-the-live-session-view-on-the-frontend (fcc9003)
- enable the user to add custome headers to the requests #29 (3f7475f)
- make tags optiona; (5228904)
- Merge branch 'main' into 9-test-failure-notifications (24de752)
- implement notifications for failed executions that ran on a schedule #9 (16be07e)
- implement notifications for failed executions that ran on a schedule #9 (cf49576)
- fix validation form issues (2056c31)
- relax form validations and include execution region in imports and exports (0f779a8)
- merge remote (b115474)
- build and deploy container image through cdk (d422ca0)
- allow outbound traffic by default (d65525b)
- tweak README, tweak Sample Makefile, remove some hardcoded resource names; add some CFN outputs (013fdd4)
- add user management (0d6b7b6)
- Merge pull request #17 from aws-samples/15-update-deployment-to-be-cdk-only (1dee70c)
- merge main (3999448)
- merge main (d03df46)
- Merge pull request #14 from aws-samples/13-relax-user-journey-validation (0965f81)
- fix validation form issues (4bb4bee)
- build and deploy container image through cdk (38f4b28)
- allow outbound traffic by default (4835a9d)
- allowing users to subscribe/unsubscribe to failed scheduled executions #9 (ec0764e)
- Merge pull request #16 from aws-samples/rpc/deployment (b340cc4)
- tweak README, tweak Sample Makefile, remove some hardcoded resource names; add some CFN outputs (f9984df)
- relax form validations and include execution region in imports and exports (fe08b84)
- cleanup (b2aa92f)
- Implement live view for browser session during execution, initial draft, needs cleanup (37fbe8d)
- Merge pull request #6 from aws-samples/1-bug-act_id-gets-stored-as-error-if-the-model-throws-an-error (0b64318)
- hide the trace option in case actId is empty or error (82768f8)
- Merge pull request #7 from aws-samples/2-feature-request-add-a-go-to-url-step-type (e4dda5c)
- add goto step allowing users to programatically change the url closes #2 (1086b59)
- [Bugfix] act_id is now correctly added to the execution step allowing users to see the trace of the failed step fixes #1 (d03ab6f)
- enable choosing a region when defining the usecase (f4a8c0d)
- update nova act version (1c8a227)
- fixing a few environments variables (053c77a)
- reduce memory and cpu of the ecs task (b503b51)
- update deployment instructions (a8051bf)
- use custom browser to execute the test (a5e9603)
- remove aplify config (373bcf9)
- remove amplify config (7949e50)
- port execution to bedrock-agent-core (880a9c9)
- cleanup (7ab20a3)
- initial commit (d7e0378)
- Initial commit (2e7bdd9)

All notable changes to this project will be documented in this file.

## [0.1.1-1] - 2025-10-22

### Documentation

- **readme**: add step for uploading Nova Act API Key Secret (f1c0830)
- **readme**: tweak post deployment steps (1de6ce3)
- **readme**: add step for uploading Nova Act API Key Secret (27f1d26)
- **readme**: tweak post deployment steps (f5e035b)

### Chores

- create sg for ecs tasks (de7ee2d)

### Other Changes

- add initial release functionallity (5e274c9)
- implement a release process (337a609)
- cleanup CDK setup and deployment instructions (ffe75d5)
- split stacks (279018f)
- cleanup makefile sample (ccb82b3)
- Merge pull request #31 from aws-samples/29-add-header-to-requests (3c9d86c)
- Merge branch 'main' into 29-add-header-to-requests (fa0373d)
- Merge pull request #28 from aws-samples/26-updating-a-test-care-requires-tags-while-creating-does-not (ebce780)
- Merge pull request #27 from aws-samples/9-test-failure-notifications (4019591)
- Merge branch 'main' into 9-test-failure-notifications (1814591)
- Merge pull request #24 from aws-samples/23-manage-userpool (4e4c237)
- Merge branch 'main' into 23-manage-userpool (86705ab)
- Merge branch 'main' into 9-test-failure-notifications (f2aecbd)
- Merge pull request #12 from aws-samples/8-embed-the-live-session-view-on-the-frontend (fcc9003)
- enable the user to add custome headers to the requests #29 (3f7475f)
- make tags optiona; (5228904)
- Merge branch 'main' into 9-test-failure-notifications (24de752)
- implement notifications for failed executions that ran on a schedule #9 (16be07e)
- implement notifications for failed executions that ran on a schedule #9 (cf49576)
- fix validation form issues (2056c31)
- relax form validations and include execution region in imports and exports (0f779a8)
- merge remote (b115474)
- build and deploy container image through cdk (d422ca0)
- allow outbound traffic by default (d65525b)
- tweak README, tweak Sample Makefile, remove some hardcoded resource names; add some CFN outputs (013fdd4)
- add user management (0d6b7b6)
- Merge pull request #17 from aws-samples/15-update-deployment-to-be-cdk-only (1dee70c)
- merge main (3999448)
- merge main (d03df46)
- Merge pull request #14 from aws-samples/13-relax-user-journey-validation (0965f81)
- fix validation form issues (4bb4bee)
- build and deploy container image through cdk (38f4b28)
- allow outbound traffic by default (4835a9d)
- allowing users to subscribe/unsubscribe to failed scheduled executions #9 (ec0764e)
- Merge pull request #16 from aws-samples/rpc/deployment (b340cc4)
- tweak README, tweak Sample Makefile, remove some hardcoded resource names; add some CFN outputs (f9984df)
- relax form validations and include execution region in imports and exports (fe08b84)
- cleanup (b2aa92f)
- Implement live view for browser session during execution, initial draft, needs cleanup (37fbe8d)
- Merge pull request #6 from aws-samples/1-bug-act_id-gets-stored-as-error-if-the-model-throws-an-error (0b64318)
- hide the trace option in case actId is empty or error (82768f8)
- Merge pull request #7 from aws-samples/2-feature-request-add-a-go-to-url-step-type (e4dda5c)
- add goto step allowing users to programatically change the url closes #2 (1086b59)
- [Bugfix] act_id is now correctly added to the execution step allowing users to see the trace of the failed step fixes #1 (d03ab6f)
- enable choosing a region when defining the usecase (f4a8c0d)
- update nova act version (1c8a227)
- fixing a few environments variables (053c77a)
- reduce memory and cpu of the ecs task (b503b51)
- update deployment instructions (a8051bf)
- use custom browser to execute the test (a5e9603)
- remove aplify config (373bcf9)
- remove amplify config (7949e50)
- port execution to bedrock-agent-core (880a9c9)
- cleanup (7ab20a3)
- initial commit (d7e0378)
- Initial commit (2e7bdd9)

All notable changes to this project will be documented in this file.

## [0.1.1-0] - 2025-10-22

### Documentation

- **readme**: add step for uploading Nova Act API Key Secret (f1c0830)
- **readme**: tweak post deployment steps (1de6ce3)
- **readme**: add step for uploading Nova Act API Key Secret (27f1d26)
- **readme**: tweak post deployment steps (f5e035b)

### Chores

- create sg for ecs tasks (de7ee2d)

### Other Changes

- implement a release process (337a609)
- cleanup CDK setup and deployment instructions (ffe75d5)
- split stacks (279018f)
- cleanup makefile sample (ccb82b3)
- Merge pull request #31 from aws-samples/29-add-header-to-requests (3c9d86c)
- Merge branch 'main' into 29-add-header-to-requests (fa0373d)
- Merge pull request #28 from aws-samples/26-updating-a-test-care-requires-tags-while-creating-does-not (ebce780)
- Merge pull request #27 from aws-samples/9-test-failure-notifications (4019591)
- Merge branch 'main' into 9-test-failure-notifications (1814591)
- Merge pull request #24 from aws-samples/23-manage-userpool (4e4c237)
- Merge branch 'main' into 23-manage-userpool (86705ab)
- Merge branch 'main' into 9-test-failure-notifications (f2aecbd)
- Merge pull request #12 from aws-samples/8-embed-the-live-session-view-on-the-frontend (fcc9003)
- enable the user to add custome headers to the requests #29 (3f7475f)
- make tags optiona; (5228904)
- Merge branch 'main' into 9-test-failure-notifications (24de752)
- implement notifications for failed executions that ran on a schedule #9 (16be07e)
- implement notifications for failed executions that ran on a schedule #9 (cf49576)
- fix validation form issues (2056c31)
- relax form validations and include execution region in imports and exports (0f779a8)
- merge remote (b115474)
- build and deploy container image through cdk (d422ca0)
- allow outbound traffic by default (d65525b)
- tweak README, tweak Sample Makefile, remove some hardcoded resource names; add some CFN outputs (013fdd4)
- add user management (0d6b7b6)
- Merge pull request #17 from aws-samples/15-update-deployment-to-be-cdk-only (1dee70c)
- merge main (3999448)
- merge main (d03df46)
- Merge pull request #14 from aws-samples/13-relax-user-journey-validation (0965f81)
- fix validation form issues (4bb4bee)
- build and deploy container image through cdk (38f4b28)
- allow outbound traffic by default (4835a9d)
- allowing users to subscribe/unsubscribe to failed scheduled executions #9 (ec0764e)
- Merge pull request #16 from aws-samples/rpc/deployment (b340cc4)
- tweak README, tweak Sample Makefile, remove some hardcoded resource names; add some CFN outputs (f9984df)
- relax form validations and include execution region in imports and exports (fe08b84)
- cleanup (b2aa92f)
- Implement live view for browser session during execution, initial draft, needs cleanup (37fbe8d)
- Merge pull request #6 from aws-samples/1-bug-act_id-gets-stored-as-error-if-the-model-throws-an-error (0b64318)
- hide the trace option in case actId is empty or error (82768f8)
- Merge pull request #7 from aws-samples/2-feature-request-add-a-go-to-url-step-type (e4dda5c)
- add goto step allowing users to programatically change the url closes #2 (1086b59)
- [Bugfix] act_id is now correctly added to the execution step allowing users to see the trace of the failed step fixes #1 (d03ab6f)
- enable choosing a region when defining the usecase (f4a8c0d)
- update nova act version (1c8a227)
- fixing a few environments variables (053c77a)
- reduce memory and cpu of the ecs task (b503b51)
- update deployment instructions (a8051bf)
- use custom browser to execute the test (a5e9603)
- remove aplify config (373bcf9)
- remove amplify config (7949e50)
- port execution to bedrock-agent-core (880a9c9)
- cleanup (7ab20a3)
- initial commit (d7e0378)
- Initial commit (2e7bdd9)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of Nova Act QA Studio
- Web-based automation platform with AI-powered browser automation
- AWS serverless architecture (API Gateway, Lambda, DynamoDB, ECS Fargate)
- React frontend with AWS Cloudscape Design System
- Cognito authentication
- Automated release system with changelog generation
