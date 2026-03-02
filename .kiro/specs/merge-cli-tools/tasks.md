# Tasks Document: Merge CLI Tools

## Task 1: Unified Error Hierarchy and Pydantic Models

- [x] Create `qa_studio_cli/models/errors.py` with unified error hierarchy: `QAStudioError` base, `AuthError`, `ConfigError`, `ApiError(status_code, message, error_code)`, `ExecutionError`
- [x] Extend `qa_studio_cli/models/config.py` `CLIConfig` with optional M2M fields: `oauth_client_id`, `oauth_client_secret`, `oauth_token_endpoint` (all `Optional[str] = None`), add `validate_optional_https_url` for `oauth_token_endpoint`
- [x] Create `qa_studio_cli/models/execution.py` with runner-specific models moved from `qa-studio-ci-runner/src/execution/models.py`: `StepResult`, `UseCaseMetadata`, `UseCaseStep`, `StepResultDetail`, `ArtifactPaths`, `LocalExecutionResult`, `RemoteExecutionResult` (remove `TokenFileData` — handled by `TokenFileProvider`)
- [x] Update all existing CLI code that imports from `qa_studio_cli.models.errors` to use the new `QAStudioError`-based hierarchy (ensure `AuthError`, `ConfigError`, `ApiError` keep the same interface)
- [x] Write unit tests for the unified error hierarchy (inheritance, `.message` attribute, `ApiError.__str__`)
- [x] Write unit tests for extended `CLIConfig` (M2M fields optional, HTTPS validation on `oauth_token_endpoint`, round-trip serialization)
- [x] Run all existing CLI tests to confirm no regressions from the model changes

**Requirements:** 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 4.6

## Task 2: Shared Configuration Module with M2M Support

- [x] Move `qa_studio_cli/utils/config.py` to `qa_studio_cli/config/manager.py`, create `qa_studio_cli/config/__init__.py`
- [x] Update `ENV_VAR_MAP` to include `oauth_client_id: OAUTH_CLIENT_ID`, `oauth_client_secret: OAUTH_CLIENT_SECRET`, `oauth_token_endpoint: OAUTH_TOKEN_ENDPOINT` as optional overlays
- [x] Update `load_config()` to handle optional M2M fields from both file and env vars (env vars override file values)
- [x] Update `save_config()` to serialize M2M fields (exclude `None` values from JSON output to keep config clean)
- [x] Update `configure` command in `cli.py` to prompt for optional M2M fields after core fields (allow empty/skip)
- [x] Update all imports across the CLI codebase from `qa_studio_cli.utils.config` to `qa_studio_cli.config.manager`
- [x] Write unit tests for config round-trip with M2M fields, env var overlay for M2M fields, `None` exclusion in JSON
- [x] Run all existing CLI tests to confirm no regressions

**Requirements:** 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7

## Task 3: Unified Authentication Module

- [x] Create `qa_studio_cli/auth/client_credentials.py` with `ClientCredentialsProvider` class: `__init__(client_id, client_secret, token_endpoint)`, `get_token() -> str`, in-memory caching with 5-minute expiry buffer, scopes matching runner's existing scopes
- [x] Create `qa_studio_cli/auth/token_file_provider.py` with `TokenFileProvider` class: `__init__(path)`, `get_token() -> str`, re-reads file on each call, validates `access_token` field exists, raises `AuthError`
- [x] Create `qa_studio_cli/auth/resolver.py` with `TokenResolver` class: resolution chain (token-file → env vars → config M2M → stored user token), `get_token() -> str`
- [x] Write unit tests for `ClientCredentialsProvider` (token request, caching, expiry, error handling)
- [x] Write unit tests for `TokenFileProvider` (valid file, missing file, missing field, re-read on each call)
- [x] Write unit tests for `TokenResolver` (priority order, fallback chain, all-sources-exhausted error)
- [x] Run all existing CLI tests to confirm no regressions

**Requirements:** 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7

## Task 4: Unified API Client

- [x] Rewrite `qa_studio_cli/api/client.py` `ApiClient` to accept `token_provider: Callable[[], str]` instead of `access_token: str`, use `requests.Session()` for connection pooling, call `token_provider()` on each request
- [x] Add `patch()` method to `ApiClient` (currently missing — needed by runner's execution API)
- [x] Update `require_auth` decorator in `api/client.py` to create `ApiClient` with a `token_provider` lambda that calls `get_valid_token()`
- [x] Move runner's API modules into `qa_studio_cli/api/`: copy `usecases.py`, `executions.py`, `test_suites.py` from `qa-studio-ci-runner/src/api/`, update imports to use unified `ApiClient` and `ApiError`
- [x] Update all API path strings in the moved runner API modules to include `/api` prefix (e.g. `/usecase/{id}` → `/api/usecase/{id}`)
- [x] Update all existing CLI command code that creates `ApiClient` to use the new `token_provider` interface
- [x] Write unit tests for unified `ApiClient` (Bearer header, all HTTP methods, error mapping for 401/403/404, session reuse)
- [x] Run all existing CLI tests to confirm no regressions

**Requirements:** 6.1, 6.2, 6.3, 6.4, 6.5, 6.6

## Task 5: Runner Module Migration

- [x] Create `qa_studio_cli/runner/` package with `__init__.py`
- [x] Copy runner execution modules from `qa-studio-ci-runner/src/execution/` to `qa_studio_cli/runner/`: `engine.py`, `step_executor.py`, `workflow_manager.py`, `artifacts.py`, `artifact_uploader.py`, `suite_log_capture.py`
- [x] Copy `qa-studio-ci-runner/src/main.py` to `qa_studio_cli/runner/main.py`
- [x] Copy `qa-studio-ci-runner/src/output/summary.py` to `qa_studio_cli/runner/output.py`
- [x] Copy runner utility modules: `qa-studio-ci-runner/src/utils/url.py` → `qa_studio_cli/utils/url.py`, `variables.py` → `qa_studio_cli/utils/variables.py`, `logger.py` → `qa_studio_cli/utils/logger.py`, `log_filters.py` → `qa_studio_cli/utils/log_filters.py`, `sanitize_error_message()` from `errors.py` → `qa_studio_cli/utils/errors.py`
- [x] Update all imports in migrated runner modules: replace `src.` / `..` imports with `qa_studio_cli.` imports, replace runner error classes with unified hierarchy (`AuthenticationError` → `AuthError`, `ConfigurationError` → `ConfigError`, `APIError` → `ApiError`, `ExecutionError` → `ExecutionError`), replace `Settings` usage with `load_config()` + `TokenResolver`
- [x] Update `runner/main.py` to use unified `ApiClient` with `TokenResolver.get_token` as `token_provider`, remove `Settings.from_env()` / `OAuthClient` usage
- [x] Ensure no runner module imports `nova_act`, `playwright`, or `boto3` at module level (all imports must be inside functions/methods)
- [ ] Run migrated runner tests (with runner extras installed) to confirm functionality

**Requirements:** 1.4, 3.6, 9.1, 9.2

## Task 6: Run Command with Lazy Import Gate

- [x] Create `qa_studio_cli/commands/run.py` with Click command matching all current ci-runner options (`--usecase-id`, `--suite-id`, `--local-only`, `--token-file`, `--base-url`, `--var`, `--region`, `--model-id`, `--timeout`, `--keep-artifacts`, `--verbose`, `--format`)
- [x] Implement lazy import gate: `try: from qa_studio_cli.runner.main import run_usecase, run_runner` with `ImportError` catch displaying install instructions
- [x] Implement mutually exclusive validation for `--usecase-id` / `--suite-id`
- [x] Wire up `TokenResolver` creation from command options (token_file, config) and pass to runner functions
- [x] Register `run` command in `cli.py`
- [x] Write unit tests for the `run` command: missing deps error message, mutually exclusive validation, option parsing
- [x] Run full CLI test suite

**Requirements:** 2.6, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 9.1, 9.2, 9.3

## Task 7: setup.py and Package Configuration

- [x] Update `qa-studio-cli/setup.py`: change `name` to `qa-studio`, add `extras_require={"runner": ["nova-act==3.1.157.0", "boto3>=1.34.0", "tenacity>=8.2.0", "playwright"]}`, keep core `install_requires` as `[click, requests, pydantic]`
- [x] Create `qa-studio-cli/requirements-runner.txt` listing runner extras for development convenience
- [x] Remove `qa_studio_cli/runner/executor.py` (dead subprocess wrapper)
- [x] Remove `qa_studio_cli/utils/config.py` if still present (moved to `config/manager.py` in Task 2)
- [ ] Verify `pip install -e .` works for core-only install
- [ ] Verify `pip install -e ".[runner]"` works with runner extras
- [ ] Run full test suite with runner extras installed

**Requirements:** 1.1, 1.2, 1.3, 1.5, 11.4

## Task 8: Test Migration and Coverage

- [x] Create `qa-studio-cli/tests/conftest.py` with `requires_runner` skip marker (check for `nova_act` import)
- [ ] Migrate runner tests from `qa-studio-ci-runner/tests/` to `qa-studio-cli/tests/`: update imports to use unified package paths, replace runner error classes with unified hierarchy
- [ ] Apply `@requires_runner` marker to all runner-specific test classes/functions
- [x] Update existing CLI tests for any import path changes (config module move, error class changes)
- [ ] Write property-based tests for design correctness properties (config round-trip, HTTPS validation, file permissions, token file re-read, Bearer header, error hierarchy)
- [ ] Run full test suite and verify ≥70% coverage
- [x] Run tests without runner extras to verify runner tests are skipped cleanly

**Requirements:** 10.1, 10.2, 10.3, 10.4

## Task 9: Docker Image Update

- [x] Update the Dockerfile to install unified package: `pip install qa-studio[runner]` instead of separate packages
- [x] Update entrypoint from `qa-studio-ci-runner` to `qa-studio run`
- [x] Verify multi-stage build pattern is maintained
- [ ] Test Docker build completes successfully

**Requirements:** 8.1, 8.2, 8.3

## Task 10: Dead Code Removal and Final Cleanup

- [x] Verify no duplicate API client implementations remain (only `qa_studio_cli/api/client.py`)
- [x] Verify no duplicate error class hierarchies remain (only `qa_studio_cli/models/errors.py`)
- [x] Verify no duplicate config loading logic remains (only `qa_studio_cli/config/manager.py`)
- [x] Verify `qa_studio_cli/runner/executor.py` (subprocess wrapper) is removed
- [x] Remove `qa_studio_cli/utils/config.py` if still present
- [x] Run full test suite one final time to confirm everything passes
- [ ] Verify the `qa-studio-ci-runner/` directory can be removed without breaking any imports or tests in the unified package

**Requirements:** 11.1, 11.2, 11.3, 11.4, 11.5
