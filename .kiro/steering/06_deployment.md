---
inclusion: always
---

* This is a CDK application.
* All build dependencies are managed through the package.json in the root of the project.
* `npm run deploy` is the point for deployments. Any additional steps need to be added into this command.
* If you want to run the deployment. check if docker is installed or podman is installed and use `CDK_DOCKER={installed container tool}` to prefix `npm run deploy`
* you must add any options added to configuration.json to the documentation
