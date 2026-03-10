---
inclusion: always
---

* This is an API first application!
* Authroization and Authentication will go through Cognito.
* All endpoints must have the authorizer attached
* All endpoints must check for the correct scopes
* Reading endpoints must always be using GET
* Writing endpoints must always use POST, PUT or PATCH
* Deleting endpoints must always use DELETE and return a 204
<!-- * All JSON returned from the API must be using camelcase -->