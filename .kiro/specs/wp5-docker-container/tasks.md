# Implementation Plan: WP5 Docker Container

## Overview

Package the existing CI/CD test runner as a Docker container using a multi-stage build. Implementation proceeds: .dockerignore → Dockerfile → Dockerfile unit tests → property-based tests → container integration tests → README documentation. All code is Python 3.12. Tests use `pytest` and `hypothesis`.

## Tasks

- [x] 1. Create .dockerignore file
  - [x] 1.1 Create `cicd-runner/.dockerignore` with all required exclusion patterns
    - Add exclusions: `venv/`, `__pycache__/`, `.pytest_cache/`, `.hypothesis/`, `htmlcov/`, `tests/`, `.env`, `.env.example`, `.coverage`, `*.egg-info/`, `.git/`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10_

  - [ ]* 1.2 Write unit tests for .dockerignore in `cicd-runner/tests/test_dockerignore.py`
    - Verify file exists at `cicd-runner/.dockerignore`
    - Verify all required patterns are present: `venv/`, `__pycache__/`, `.pytest_cache/`, `.hypothesis/`, `htmlcov/`, `tests/`, `.env`, `.env.example`, `.coverage`, `*.egg-info/`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10_

- [x] 2. Create multi-stage Dockerfile
  - [x] 2.1 Create `cicd-runner/Dockerfile` with builder and runtime stages
    - Builder stage: `python:3.12-slim` base, set `NOVA_ACT_SKIP_PLAYWRIGHT_INSTALL=true`, create venv at `/app/.venv`, `pip install --no-cache-dir` requirements and package
    - Runtime stage: `python:3.12-slim` base, install Playwright Chromium with `--with-deps`, clean apt lists, create `runner` user (uid 1000), copy venv from builder, copy browser cache to runner user, create `/app/logs` with runner ownership, set env vars, set `ENTRYPOINT ["cicd-runner"]`
    - Follow patterns from `worker/Dockerfile` and Nova Act SDK template
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 6.1, 6.2_

- [x] 3. Checkpoint - Verify Dockerfile builds
  - Ensure the Dockerfile builds successfully with `docker build -t cicd-runner .` from the `cicd-runner/` directory. Ask the user if questions arise.

- [ ] 4. Write Dockerfile structure tests
  - [ ]* 4.1 Write unit tests for Dockerfile structure in `cicd-runner/tests/test_dockerfile.py`
    - Parse Dockerfile as text and verify:
    - `test_has_two_from_statements` — multi-stage build with builder and runtime stages
    - `test_builder_uses_python_312_slim` — builder base image is `python:3.12-slim`
    - `test_runtime_uses_python_312_slim` — runtime base image is `python:3.12-slim`
    - `test_builder_sets_skip_playwright_env` — `NOVA_ACT_SKIP_PLAYWRIGHT_INSTALL=true` before pip install
    - `test_builder_uses_no_cache_dir` — `pip install --no-cache-dir`
    - `test_runtime_installs_playwright_chromium` — `playwright install --with-deps chromium`
    - `test_playwright_install_before_user_directive` — Playwright install happens before `USER` directive
    - `test_browser_cache_copied_to_runner` — browser cache copied from root to runner user
    - `test_creates_runner_user` — `useradd` with uid 1000
    - `test_sets_user_runner` — `USER runner` in runtime stage
    - `test_entrypoint_is_cicd_runner` — `ENTRYPOINT` uses `cicd-runner`
    - `test_cleans_apt_lists` — `rm -rf /var/lib/apt/lists/*`
    - `test_runtime_sets_skip_playwright_env` — runtime sets `NOVA_ACT_SKIP_PLAYWRIGHT_INSTALL=true`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 4.1, 6.1, 6.2_

- [ ] 5. Write property-based tests
  - [ ]* 5.1 Write property test for CLI argument passthrough in `cicd-runner/tests/test_docker_properties.py`
    - **Property 1: CLI argument passthrough**
    - Use `hypothesis` to generate random valid CLI argument combinations from known flags (`--suite-id`, `--base-url`, `--var`, `--region`, `--model-id`, `--verbose`, `--timeout`)
    - Invoke the Click CLI parser with generated args and verify it parses them correctly without error
    - Minimum 100 iterations
    - **Validates: Requirements 4.2**

  - [ ]* 5.2 Write property test for missing env var validation in `cicd-runner/tests/test_docker_properties.py`
    - **Property 2: Missing required env var produces exit code 2 with identifying message**
    - Use `hypothesis` to generate random valid values for all required env vars (`OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `OAUTH_TOKEN_ENDPOINT`, `API_ENDPOINT`)
    - For each required var, omit it while setting all others, call `Settings.from_env()`, verify `ConfigurationError` is raised and message contains the missing variable name
    - Minimum 100 iterations
    - **Validates: Requirements 5.6**

- [ ] 6. Write container integration tests
  - [ ]* 6.1 Write container integration tests in `cicd-runner/tests/test_container_integration.py`
    - These tests require a built Docker image and Docker daemon
    - Mark with `@pytest.mark.integration` so they can be skipped in CI without Docker
    - `test_help_exits_zero` — `docker run <image> --help` exits 0 and shows usage text
    - `test_cicd_runner_on_path` — `docker run <image> which cicd-runner` finds CLI on PATH
    - `test_runs_as_non_root_user` — `docker run <image> id` shows uid 1000
    - `test_logs_directory_writable` — `docker run <image> touch /app/logs/test.log` succeeds
    - `test_missing_env_var_exits_2` — running without required env vars exits with code 2
    - `test_image_size_under_2gb` — `docker image inspect` shows size under 2GB
    - _Requirements: 4.3, 3.3, 9.1, 9.2, 9.3, 5.6, 6.4_

- [ ] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass (excluding integration tests if Docker is unavailable). Ask the user if questions arise.

- [x] 8. Update README with Docker documentation
  - [x] 8.1 Add Docker build and run sections to `cicd-runner/README.md`
    - Add "Docker" section with build command: `docker build -t cicd-runner .`
    - Add run command with all required environment variables (`-e OAUTH_CLIENT_ID=... -e OAUTH_CLIENT_SECRET=... -e OAUTH_TOKEN_ENDPOINT=... -e API_ENDPOINT=...`)
    - Document optional env vars (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `LOG_LEVEL`)
    - Document minimum resource requirements (memory: 2GB recommended, CPU: 2 cores)
    - _Requirements: 7.1, 7.2, 7.4, 7.5_

  - [x] 8.2 Add CI/CD integration examples to `cicd-runner/README.md`
    - Add GitHub Actions example workflow snippet
    - Add GitLab CI example `.gitlab-ci.yml` snippet
    - Add Jenkins pipeline example snippet
    - Each example shows how to pass secrets as env vars and run with `--suite-id`
    - _Requirements: 7.3_

  - [ ]* 8.3 Write unit tests for README content in `cicd-runner/tests/test_readme.py`
    - Parse README as text and verify:
    - `test_readme_has_docker_build_section` — contains `docker build` command
    - `test_readme_has_docker_run_section` — contains `docker run` with env vars
    - `test_readme_has_github_actions_example` — contains GitHub Actions snippet
    - `test_readme_has_gitlab_ci_example` — contains GitLab CI snippet
    - `test_readme_has_jenkins_example` — contains Jenkins snippet
    - `test_readme_documents_all_required_env_vars` — lists all 4 required env vars
    - `test_readme_documents_resource_requirements` — mentions memory and CPU
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests use `hypothesis` (already in `requirements-dev.txt`)
- Container integration tests require Docker daemon and are marked `@pytest.mark.integration`
- The Dockerfile follows established patterns from `worker/Dockerfile` and Nova Act SDK template
- No changes to existing Python source code are needed — the container packages the existing CLI as-is
