---
inclusion: always
---

* Understand the available code first
* Well tested code is non-negotiable; I rather have too many tests than to few
* I want code that is "engineered enough" – not under-engineered (flacky, hacky) and not over engineered (premature abstraction, unnecessary complexity)
* Bias towards exclicit over clever
* Evaluate code organization and module structure
* Read code that is relevant to the current task
* DRY is important – flag repitition agressivly
* Always ensure OAuth scopes exists.
* Always read all related code carefully and extensive.
* Always remove dead/unused code, when in doubt ask
* When deleting code remove all parts and check for endpoints that are not reachable afterwards
* Aim for 70% unit test coverage
* For new features also build end 2 end tests. How you can build those can be found in the prompt inside lambdas/endpoints/generate_userjourney.py lambda in the endpoints directory
* All datamodels should be defined in pydantic
* after finishing a coding task make sure that all UI tests are running. use the `qa-studio` skill to find the best suites or tests matching the changed user flows
* when adding new userflows or updates to the UI use `qa-studio` skill to create new test cases using the user journey mode based on the user journey section in the design document.
* Always commit any changes after finishing a coding task with an an concise apappropiate one line commit message
