---
inclusion: always
---

* This is a CDK application.
* All build dependencies are managed through the package.json in the root of the project.
* `npm run deploy` is the point for deployments. Any additional steps need to be added into this command.
* The deployment needs no container tool (no Docker/Podman, no `CDK_DOCKER`): the worker is a Lambda MicroVM image that AWS Lambda builds from a zip the CDK app uploads (`web-app/lib/worker-image-asset.ts`, local bundling = file copy).
* A worker deploy (`npm run deploy:worker`, also part of `npm run deploy`) rebuilds the MicroVM image whenever anything under `web-app/worker/` or `qa-studio-cli/` changed (README edits included); CloudFormation waits 3–5 min for the build. Build logs: `/qa-studio/<baseName>/microvm`, stream `<version>/<build-id>`.
* `loadConfig()` rejects the configuration keys of the removed ECS worker runtime (`REMOVED_CONFIG_KEYS` in `web-app/lib/config.ts`: `workerRuntime`, `dockerImageVersion`, listed in `docs/configuration.md` → Removed keys); never re-add them. `agentCoreVPC` / `createVpcEndpoints` are deprecated (`DEPRECATED_CONFIG_KEYS`, warning, ignored); no module may read them.
* `vpcId` only attaches the AgentCore browsers to an imported VPC (`lib/browser-vpc.ts`): lookup, at most one created security group, `AGENT_CORE_VPC`/`AC_*` image env. The stack never creates a VPC, NAT gateway, endpoint or route; synth with `vpcId` needs AWS credentials and the AWS CLI.
* you must add any options added to configuration.json to the documentation
