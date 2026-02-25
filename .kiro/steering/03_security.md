---
inclusion: always
---

* Cognito is used for user and m2m authentication / authorization
* Scopes are always structured like this api/{scope_name}.read or write
* All api endpoints must validate for the correct scope, ask if you're unsure about the correct scope.
* GET request should alwaus have a reading scope
* PUT, PATCH, POST, DELETE should always have a writing scope
* When creating a new Oauth-client you cannot grant more scopes that the user has attached
* Ensure all OAuth scopes use the plural – and exists within the CDK stack before using them, if a scope does not exists ask before using it and adding it to the CDK stack.
* Never store sensitive data in clear text files