---
inclusion: always
---

This is about learning:

* If you had any learnings write them into this document under the learnings headline.
* Only add key learnings and stay concise in the learning description.
* When you're unsure wheater to add or not ask me.
* You can decide by yourself if you want to add any learnings.
* Learnings need to be concise and precise

----

## learnings

* Use Grid component with gridDefinition for responsive layouts instead of ColumnLayout. Pattern: `gridDefinition={[{ colspan: { default: 12, m: 9 } }, { colspan: { default: 12, m: 3 } }]}` creates a 9:3 column split on medium+ screens and full-width stacking on mobile.
* Execution status values: use `"success"` / `"failed"` (not `"completed"`). Applies to both usecase-level and step-level statuses.
* Never place early returns (e.g. `if (!id) return <Box>...`) between `useState` and `useEffect` hooks — violates React Rules of Hooks. Move the guard after all hooks.
* When running sync code inside `asyncio.to_thread`, you cannot use `asyncio.run()` or `loop.run_until_complete()` — Nova Act/Playwright runs its own event loop on the thread, blocking both approaches. Use `concurrent.futures.ThreadPoolExecutor` to dispatch async calls to a disposable thread with its own `asyncio.new_event_loop()`.
* When a DynamoDB GSI indexes on an attribute (e.g. `suite_execution_id`), ALL records with that attribute are returned — including metadata records that happen to share the attribute. Always filter GSI results by `pk` prefix to exclude unintended record types.
* DynamoDB `update_item` with non-existent keys silently creates a new record (upsert). Always verify PK/SK in update calls match the keys used in the original `put_item`.
* DynamoDB items returned by the API use snake_case field names (e.g. `step_type`, `actual_value`). Frontend components must use snake_case — not camelCase — when accessing these fields.
* API Gateway path parameter names must match the CDK resource definition exactly. CDK uses `{suite_id}` / `{execution_id}` (snake_case), so lambdas must read `event['pathParameters']['suite_id']` — not `suiteId` (camelCase).
* Click 8.x removed `mix_stderr` from `CliRunner`. Stderr output from `click.echo(..., err=True)` goes into `result.output` by default. Check `result.output` instead of `result.stderr` in Click CLI tests.
* Cognito Lite tier does NOT include resource server scopes in the access token for authorization code flow (user tokens). `scopesToAdd` in V2 pre-token-generation requires Essentials/Plus. Workaround: resolve scopes from `cognito:groups` (always present in access tokens) in the Lambda authorizer using a group-to-scope mapping.
* When adding new OAuth scopes to the CDK auth stack resource server, also add them to `GROUP_SCOPE_MAPPINGS` in `authorizer.py` and `SCOPE_MAPPINGS` in `pre_token_generation.py` — keep all three in sync.
* DynamoDB reserved keywords (e.g. `name`, `status`, `count`) cannot be used directly in UpdateExpression. Use `ExpressionAttributeNames` with aliases like `#n` for `name`. Full list: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ReservedWords.html
* Lambda functions using `Code.fromAsset()` only package the specified directory. Shared modules must be copied into the Lambda deployment directory or provided via Lambda Layers. Using `sys.path` manipulation only works for local testing, not Lambda deployment.
* Nova Act artifacts are stored at `{usecase_id}/{execution_id}/{session_id}/act_{act_id}.json` in S3. The session_id is the Nova Act session ID obtained via `nova.get_session_id()`. Browser recordings use `/recording/` subdirectory but Nova Act artifacts do not.
* Endpoint lambdas using third-party deps (e.g. pydantic) must `import lambda_init` as their first import — this adds the `dependencies/` folder to `sys.path`. The `lambda:install-deps` script must run before deploy (now part of `npm run deploy`).
* `pip install -t` installs native binaries for the host platform. Lambda ARM64 (Python 3.13) needs `--platform manylinux2014_aarch64 --implementation cp --python-version 3.13 --only-binary=:all:` to get Linux-compatible `.so` files instead of macOS darwin ones.
* EXECUTION_STEP SK is `EXECUTION_STEP#{uuid7}`, not `EXECUTION_STEP#{sort}`. The `sort` field is a separate numeric attribute. To find a step by its sort/position value, query all `EXECUTION_STEP#` records under the execution PK and filter by `sort`.
* When `lambda_init` adds a `dependencies/` folder with Linux ARM64 binaries to `sys.path`, local macOS tests break on native modules (e.g. pydantic_core). Use a `conftest.py` that stubs `lambda_init` via `sys.modules` before test imports.
* Nova Act `_calls.json` screenshot fields already include the full data URI prefix (`data:image/jpeg;base64,...`). Don't add another `data:image/...;base64,` wrapper in the frontend — use the value directly as the `img src`.
* `execute_usecase` trigger types: `OnDemand` sends to SQS (deprecated, no consumer), `OnDemandHeadless` directly spawns ECS tasks, `Scheduled` also spawns ECS directly, `ci_runner` creates DB records only. For suite execution from UI, use `OnDemandHeadless` to actually run tests. Also: `execute_usecase` reads `trigger-type`, `suite-execution-id`, `suite-id` from `queryStringParameters`, not from the request body.
