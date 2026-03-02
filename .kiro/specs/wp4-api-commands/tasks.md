# Implementation Plan: WP4 API Wrapper Commands

## Overview

Add API wrapper commands to the QA Studio CLI for test (usecase) and suite management. Implementation order: error model → Pydantic API models → ApiClient + require_auth decorator → tests commands → suites commands → CLI registration → tests. All HTTP requests are mocked in tests — no real network calls.

## Tasks

- [x] 1. Add ApiError to error models and create Pydantic API response models
  - [x] 1.1 Add `ApiError` to `qa-studio-cli/qa_studio_cli/models/errors.py`
    - Add `ApiError(Exception)` with `status_code: int`, `message: str`, `error_code: str | None`
    - Implement `__str__` returning `[{status_code}] {message}` (with `({error_code})` suffix when present)
    - _Requirements: 13.1, 13.2_

  - [x] 1.2 Create `qa-studio-cli/qa_studio_cli/models/api.py`
    - Define `UsecaseModel(BaseModel)` with `alias_generator=to_camel`, `populate_by_name=True`
    - Fields: `id`, `name`, `description`, `starting_url`, `active`, `tags`, `created_at`, `executing_region`, `model_id` (all with defaults except `id` and `name`)
    - Define `SuiteModel(BaseModel)` with same config
    - Fields: `id`, `name`, `description`, `tags`, `created_at`, `created_by`, `total_usecases`
    - Define `SuiteExecutionResponse(BaseModel)` with fields: `suite_execution_id`, `suite_id`, `status`, `created_at`, `execution_ids`
    - Define `GenerateUsecaseResponse(BaseModel)` with fields: `success`, `usecase_data`, `message`
    - Define `ImportUsecaseResponse(BaseModel)` with fields: `success`, `usecase_id`, `message`
    - _Requirements: 2.1, 2.2, 2.3_


  - [x]* 1.3 Write property test: ApiError string representation (Property 4)
    - **Property 4: ApiError string representation**
    - For any integer status code and any non-empty message string, `str(ApiError(status_code, message))` contains both the status code and the message
    - Test file: `qa-studio-cli/tests/test_api_models.py`
    - **Validates: Requirements 13.2**

  - [x]* 1.4 Write property test: camelCase to snake_case model round-trip (Property 5)
    - **Property 5: camelCase to snake_case model round-trip**
    - For any valid `UsecaseModel` instance, serializing via `model_dump(by_alias=True)` and parsing back produces an equal instance; same for `SuiteModel`
    - Test file: `qa-studio-cli/tests/test_api_models.py`
    - **Validates: Requirements 2.1, 2.2, 2.3**

  - [x]* 1.5 Write property test: Invalid API responses raise validation errors (Property 6)
    - **Property 6: Invalid API responses raise validation errors**
    - For any JSON dict missing the required `id` field, constructing `UsecaseModel` or `SuiteModel` raises `ValidationError`
    - Test file: `qa-studio-cli/tests/test_api_models.py`
    - **Validates: Requirements 2.4**

  - [x]* 1.6 Write unit tests for API models (`qa-studio-cli/tests/test_api_models.py`)
    - Test `UsecaseModel` accepts camelCase JSON and exposes snake_case fields
    - Test `UsecaseModel` accepts snake_case JSON (populate_by_name)
    - Test `SuiteModel` accepts camelCase JSON and exposes snake_case fields
    - Test `ApiError.__str__()` includes status code and message
    - Test `ApiError.__str__()` includes error_code when present
    - Test all response models accept camelCase input
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 13.1, 13.2_

- [x] 2. Checkpoint - Ensure model tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement ApiClient and require_auth decorator
  - [x] 3.1 Create `qa-studio-cli/qa_studio_cli/api/__init__.py`
    - Empty init file to make `api` a Python package
    - _Requirements: 1.1_

  - [x] 3.2 Create `qa-studio-cli/qa_studio_cli/api/client.py`
    - Implement `ApiClient` class with `__init__(self, base_url: str, access_token: str)`
    - Implement `get(path, params=None)` → authenticated GET, returns parsed JSON
    - Implement `post(path, json_body=None)` → authenticated POST, returns parsed JSON
    - Implement `delete(path)` → authenticated DELETE, returns parsed JSON or None for 204
    - Implement `_request(method, path, **kwargs)` → sets `Authorization: Bearer <token>` and `Content-Type: application/json` headers, calls `requests.request`, handles `ConnectionError`/`Timeout`
    - Implement `_handle_error(response)` → maps 401 to "session expired", 403 to "insufficient permissions", 404 to "resource not found", other non-2xx to status code + message
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10_

  - [x] 3.3 Add `require_auth` decorator to `qa-studio-cli/qa_studio_cli/api/client.py`
    - Check `config_exists()` → error with "run configure" if missing
    - Call `load_config()` and `get_valid_token()`
    - Handle `ConfigError` and `AuthError` → display message to stderr, exit 1
    - Create `ApiClient(base_url=config.api_url, access_token=token)` and attach to `ctx.obj["client"]`
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 1.3, 1.4_

  - [x]* 3.4 Write property test: Auth headers on every request (Property 1)
    - **Property 1: Auth headers on every request**
    - For any access token string and any request path, every outgoing HTTP request includes `Authorization: Bearer <token>` and `Content-Type: application/json`
    - Test file: `qa-studio-cli/tests/test_api_client.py`
    - **Validates: Requirements 1.2**

  - [x]* 3.5 Write property test: 2xx responses return parsed JSON (Property 2)
    - **Property 2: 2xx responses return parsed JSON**
    - For any valid JSON response body and any 2xx status code (excluding 204), `ApiClient` returns the parsed JSON body
    - Test file: `qa-studio-cli/tests/test_api_client.py`
    - **Validates: Requirements 1.6**

  - [x]* 3.6 Write property test: Non-2xx raises ApiError with code and message (Property 3)
    - **Property 3: Non-2xx status codes raise ApiError with code and message**
    - For any non-2xx status code (excluding 401/403/404) and any error message, `_handle_error` raises `ApiError` with matching `status_code` and `message`
    - Test file: `qa-studio-cli/tests/test_api_client.py`
    - **Validates: Requirements 1.10**

  - [x]* 3.7 Write unit tests for ApiClient (`qa-studio-cli/tests/test_api_client.py`)
    - Test `get()` sends GET with correct URL and auth headers
    - Test `post()` sends POST with JSON body
    - Test `delete()` sends DELETE, returns None for 204
    - Test `_handle_error()` maps 401 → "session expired" message
    - Test `_handle_error()` maps 403 → "insufficient permissions" message
    - Test `_handle_error()` maps 404 → "resource not found" message
    - Test `_handle_error()` maps 500 → includes status code and body message
    - Test `ApiClient` handles `requests.ConnectionError` gracefully
    - Test `require_auth` creates ApiClient when config and token exist
    - Test `require_auth` exits with message when config missing
    - Test `require_auth` exits with message when token missing/expired
    - _Requirements: 1.1–1.10, 14.1–14.4_

- [x] 4. Checkpoint - Ensure API client tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement tests command group
  - [x] 5.1 Create `qa-studio-cli/qa_studio_cli/commands/__init__.py`
    - Empty init file to make `commands` a Python package
    - _Requirements: 3.1_

  - [x] 5.2 Create `qa-studio-cli/qa_studio_cli/commands/tests.py`
    - Define `tests` Click group: `@click.group()` with docstring "Manage tests (usecases)."
    - Implement `list` command: GET `/usecases`, validate with `UsecaseModel`, display table (name, ID), handle empty list
    - Implement `get <id>` command: GET `/usecase/<id>`, validate with `UsecaseModel`, display all fields (name, description, starting_url, active, region, model, tags, created_at), handle 404
    - Implement `create --from-journey` command: prompt for title, starting URL, user journey, region; POST `/generate-usecase`; POST `/import`; display created test ID and name; handle generation failure
    - Implement `delete <id>` command: prompt for confirmation (skip with `--yes`), DELETE `/usecase/<id>`, display confirmation, handle 404
    - All commands decorated with `@require_auth`, catch `ApiError` → stderr + exit 1
    - _Requirements: 3.1–3.4, 4.1–4.3, 5.1–5.5, 6.1–6.5, 13.3_

  - [x]* 5.3 Write property test: List output contains all resource identifiers (Property 7 — tests)
    - **Property 7: List output contains all resource identifiers (tests)**
    - For any non-empty list of `UsecaseModel` instances, CLI output of `tests list` contains every test's `name` and `id`
    - Test file: `qa-studio-cli/tests/test_tests_commands.py`
    - **Validates: Requirements 3.2**

  - [x]* 5.4 Write property test: Detail output contains all specified fields (Property 8 — tests)
    - **Property 8: Detail output contains all specified fields (tests)**
    - For any `UsecaseModel` with non-empty field values, CLI output of `tests get` contains name, description, starting_url, active, executing_region, model_id, tags, created_at
    - Test file: `qa-studio-cli/tests/test_tests_commands.py`
    - **Validates: Requirements 4.2**

  - [x]* 5.5 Write property test: ApiError propagation to stderr (Property 9)
    - **Property 9: ApiError propagation to stderr with exit code 1**
    - For any command decorated with `@require_auth`, when `ApiClient` raises `ApiError`, CLI writes error to stderr and exits with code 1
    - Test file: `qa-studio-cli/tests/test_tests_commands.py`
    - **Validates: Requirements 3.4, 13.3**

  - [x]* 5.6 Write unit tests for tests commands (`qa-studio-cli/tests/test_tests_commands.py`)
    - Test `tests list` displays table with names and IDs
    - Test `tests list` shows "no tests found" for empty response
    - Test `tests list` shows error and exits 1 on API failure
    - Test `tests get <id>` displays all test fields
    - Test `tests get <id>` shows "not found" on 404
    - Test `tests create --from-journey` prompts for all inputs and calls generate + import
    - Test `tests create --from-journey` shows error on generation failure
    - Test `tests delete <id>` prompts for confirmation
    - Test `tests delete <id> --yes` skips confirmation
    - Test `tests delete <id>` shows "not found" on 404
    - _Requirements: 3.1–3.4, 4.1–4.3, 5.1–5.5, 6.1–6.5_

- [x] 6. Checkpoint - Ensure tests command tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement suites command group
  - [x] 7.1 Create `qa-studio-cli/qa_studio_cli/commands/suites.py`
    - Define `suites` Click group: `@click.group()` with docstring "Manage test suites."
    - Implement `list` command: GET `/test-suites`, validate with `SuiteModel`, display table (name, ID, total_usecases), handle empty list
    - Implement `get <id>` command: GET `/test-suites/<id>`, validate with `SuiteModel`, display all fields (name, description, tags, total_usecases, created_by, created_at), handle 404
    - Implement `create` command: `--name` (required), `--description` (required), `--tags` (multiple, optional); validate name not empty/whitespace client-side; POST `/test-suites`; display created suite ID and name
    - Implement `add-tests <suite-id> <usecase-ids...>` command: POST `/test-suites/<id>/usecases` with usecase ID list; display count added and new total; handle 404
    - Implement `remove-test <suite-id> <usecase-id>` command: DELETE `/test-suites/<id>/usecases/<id>`; display confirmation; handle 404
    - Implement `run <suite-id>` command: accept `--base-url`, `--var KEY=VALUE` (multiple), `--region`, `--model-id`; POST `/test-suites/<id>/execute` with `trigger_type=ci_runner` and overrides; display suite execution ID and execution count; handle 400 errors (empty suite, unresolved variables)
    - All commands decorated with `@require_auth`, catch `ApiError` → stderr + exit 1
    - _Requirements: 7.1–7.3, 8.1–8.3, 9.1–9.4, 10.1–10.3, 11.1–11.3, 12.1–12.5, 13.3_

  - [x]* 7.2 Write property test: List output contains all resource identifiers (Property 7 — suites)
    - **Property 7: List output contains all resource identifiers (suites)**
    - For any non-empty list of `SuiteModel` instances, CLI output of `suites list` contains every suite's `name`, `id`, and `total_usecases`
    - Test file: `qa-studio-cli/tests/test_suites_commands.py`
    - **Validates: Requirements 7.2**

  - [x]* 7.3 Write property test: Detail output contains all specified fields (Property 8 — suites)
    - **Property 8: Detail output contains all specified fields (suites)**
    - For any `SuiteModel` with non-empty field values, CLI output of `suites get` contains name, description, tags, total_usecases, created_by, created_at
    - Test file: `qa-studio-cli/tests/test_suites_commands.py`
    - **Validates: Requirements 8.2**

  - [x]* 7.4 Write property test: Suite run override flags map to request body (Property 10)
    - **Property 10: Suite run override flags map to request body**
    - For any combination of `--base-url`, `--var KEY=VALUE`, `--region`, `--model-id`, the POST body contains corresponding fields and `trigger_type` is always `ci_runner`
    - Test file: `qa-studio-cli/tests/test_suites_commands.py`
    - **Validates: Requirements 12.2**

  - [x]* 7.5 Write property test: Empty/whitespace suite name rejected client-side (Property 11)
    - **Property 11: Empty/whitespace suite name rejected client-side**
    - For any string composed entirely of whitespace (including empty), `suites create --name <that string>` displays validation error and exits non-zero without API call
    - Test file: `qa-studio-cli/tests/test_suites_commands.py`
    - **Validates: Requirements 9.4**

  - [x]* 7.6 Write unit tests for suites commands (`qa-studio-cli/tests/test_suites_commands.py`)
    - Test `suites list` displays table with names, IDs, and totals
    - Test `suites list` shows "no suites found" for empty response
    - Test `suites get <id>` displays all suite fields
    - Test `suites get <id>` shows "not found" on 404
    - Test `suites create --name --description` sends POST and displays result
    - Test `suites create` with empty name shows validation error
    - Test `suites create --tags` sends tags array
    - Test `suites add-tests` sends POST with usecase IDs
    - Test `suites add-tests` shows "not found" on 404
    - Test `suites remove-test` sends DELETE and shows confirmation
    - Test `suites remove-test` shows "not found" on 404
    - Test `suites run` sends POST with `trigger_type=ci_runner`
    - Test `suites run --base-url --var --region --model-id` includes overrides in body
    - Test `suites run` shows error on empty suite (400)
    - Test `suites run` shows error on unresolved variables (400)
    - _Requirements: 7.1–7.3, 8.1–8.3, 9.1–9.4, 10.1–10.3, 11.1–11.3, 12.1–12.5_

- [x] 8. Checkpoint - Ensure suites command tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Register command groups and add test fixtures
  - [x] 9.1 Modify `qa-studio-cli/qa_studio_cli/cli.py`
    - Import `tests` group from `qa_studio_cli.commands.tests`
    - Import `suites` group from `qa_studio_cli.commands.suites`
    - Register both with `cli.add_command(tests)` and `cli.add_command(suites)`
    - _Requirements: 3.1, 7.1_

  - [x] 9.2 Update `qa-studio-cli/tests/conftest.py`
    - Add `mock_api_client` fixture: mock `ApiClient` for command tests
    - Add `cli_runner` fixture: provide Click `CliRunner`
    - Add `auth_context` fixture: patch `require_auth` to inject mock client without real auth
    - _Requirements: 15.2_

- [x] 10. Final checkpoint - Ensure all tests pass and coverage ≥70%
  - Ensure all tests pass, ask the user if questions arise.
  - Run `python -m pytest tests/ -v --cov=qa_studio_cli.api --cov=qa_studio_cli.commands --cov=qa_studio_cli.models` in `qa-studio-cli/` and verify ≥70% coverage
  - _Requirements: 15.1, 15.2, 15.3, 15.4_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (11 properties total)
- Unit tests validate specific examples and edge cases
- All HTTP requests mocked via `unittest.mock.patch` — no real network calls
- All data models use Pydantic v2 with `alias_generator=to_camel` and `populate_by_name=True`
- The backend uses `/usecases` (plural) for list and `/usecase` (singular) for CRUD — the CLI must match exactly
- JSON from the API is camelCase; Python code uses snake_case via Pydantic alias_generator
- Tests run from `qa-studio-cli/` directory: `python -m pytest tests/ -v`
