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
* Validate that functionality is given by using `qa-studio` to determine ui tests that need to be executed. During development all tests MUST execute local only
* when adding new userflows or updates to the UI use `qa-studio` to create new test cases
