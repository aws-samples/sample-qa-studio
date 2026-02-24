# Requirements Document

## Introduction

Package the existing CI/CD test runner (Python CLI at `cicd-runner/`) as a Docker container so it can be executed in any CI/CD platform (GitHub Actions, GitLab CI, Jenkins, etc.). The container must include the Nova Act SDK, a headless Chromium browser, and all dependencies. It should be optimized for size (~500MB target), run as a non-root user, and accept configuration via environment variables and CLI arguments.

## Glossary

- **Runner**: The Python CLI application at `cicd-runner/` that executes Nova Act QA Studio test suites
- **Container**: The Docker image packaging the Runner with all runtime dependencies
- **Dockerfile**: The build definition file that produces the Container image
- **Nova_Act_SDK**: The `nova-act` Python package (v3.1.157.0) used to execute browser-based test steps
- **Playwright_Chromium**: The Chromium browser installed via Playwright, required by Nova_Act_SDK for headless browser automation
- **Multi_Stage_Build**: A Docker build pattern using separate builder and runtime stages to reduce final image size
- **Entrypoint**: The container command that invokes the Runner CLI
- **Non_Root_User**: A dedicated unprivileged Linux user (uid 1000) under which the Runner process executes
- **CI_CD_Platform**: An external system (GitHub Actions, GitLab CI, Jenkins) that runs the Container as part of a pipeline

## Requirements

### Requirement 1: Multi-Stage Docker Build

**User Story:** As a DevOps engineer, I want the runner packaged as a Docker image using a multi-stage build, so that the final image is small and free of build-time dependencies.

#### Acceptance Criteria

1. THE Dockerfile SHALL use a multi-stage build with a builder stage and a runtime stage
2. THE builder stage SHALL use `python:3.12-slim` as the base image
3. THE runtime stage SHALL use `python:3.12-slim` as the base image
4. THE builder stage SHALL install Python dependencies into a virtual environment using `pip install --no-cache-dir`
5. THE builder stage SHALL set `NOVA_ACT_SKIP_PLAYWRIGHT_INSTALL=true` to skip automatic Playwright browser download during pip install
6. THE runtime stage SHALL copy only the virtual environment from the builder stage
7. THE Dockerfile SHALL reside at `cicd-runner/Dockerfile`

### Requirement 2: Playwright Chromium Browser Installation

**User Story:** As a DevOps engineer, I want the container to include a pre-installed headless Chromium browser, so that Nova Act SDK can execute browser-based tests without downloading browsers at runtime.

#### Acceptance Criteria

1. THE Dockerfile SHALL install Playwright Chromium and its OS-level dependencies using `python -m playwright install --with-deps chromium`
2. THE Dockerfile SHALL install Playwright Chromium as the root user before switching to the Non_Root_User
3. THE Dockerfile SHALL copy the Playwright browser cache from the root user's home directory to the Non_Root_User's home directory
4. THE Container SHALL set `NOVA_ACT_SKIP_PLAYWRIGHT_INSTALL=true` as a runtime environment variable to prevent Nova_Act_SDK from attempting browser installation at execution time
5. WHEN the Runner executes a test, THE Playwright_Chromium SHALL run in headless mode

### Requirement 3: Non-Root User Execution

**User Story:** As a security engineer, I want the runner to execute as a non-root user inside the container, so that the attack surface is minimized.

#### Acceptance Criteria

1. THE Dockerfile SHALL create a dedicated Non_Root_User named `runner` with uid 1000
2. THE Dockerfile SHALL set the Non_Root_User as the default user for the runtime stage
3. THE Container SHALL execute the Runner process as the Non_Root_User
4. THE Non_Root_User SHALL have read and execute permissions on the application code and virtual environment
5. THE Non_Root_User SHALL have write permissions to a `/app/logs` directory for log file output

### Requirement 4: Container Entrypoint

**User Story:** As a DevOps engineer, I want the container to use the `cicd-runner` CLI as its entrypoint, so that I can pass CLI arguments directly when running the container.

#### Acceptance Criteria

1. THE Container SHALL use the `cicd-runner` CLI command as its ENTRYPOINT
2. WHEN a CI_CD_Platform runs the Container with CLI arguments, THE Container SHALL pass those arguments to the Runner CLI
3. WHEN a CI_CD_Platform runs the Container with `--help`, THE Container SHALL display the Runner CLI help text and exit with code 0
4. WHEN a CI_CD_Platform runs the Container with `--suite-id <id>`, THE Runner SHALL execute the specified test suite

### Requirement 5: Environment Variable Configuration

**User Story:** As a DevOps engineer, I want to configure the runner via environment variables, so that I can inject credentials and endpoints from my CI/CD platform's secret management.

#### Acceptance Criteria

1. THE Container SHALL require the environment variable `OAUTH_CLIENT_ID` for OAuth authentication
2. THE Container SHALL require the environment variable `OAUTH_CLIENT_SECRET` for OAuth authentication
3. THE Container SHALL require the environment variable `OAUTH_TOKEN_ENDPOINT` for the Cognito token endpoint URL
4. THE Container SHALL require the environment variable `API_ENDPOINT` for the platform API base URL
5. THE Container SHALL accept AWS credentials via environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`) or via an IAM role for Nova_Act_SDK Bedrock access
6. IF a required environment variable is missing, THEN THE Runner SHALL exit with code 2 and log a descriptive error message identifying the missing variable

### Requirement 6: Image Size Optimization

**User Story:** As a DevOps engineer, I want the container image to be as small as practical, so that CI/CD pipeline startup times are minimized.

#### Acceptance Criteria

1. THE Dockerfile SHALL use `--no-cache-dir` for all pip install commands to avoid caching downloaded packages
2. THE Dockerfile SHALL remove apt package lists after installing OS-level dependencies using `rm -rf /var/lib/apt/lists/*`
3. THE Dockerfile SHALL use a `.dockerignore` file to exclude development files, test files, virtual environments, and caches from the build context
4. THE Container image size SHALL be at most 2GB (target ~500MB, hard limit 2GB)

### Requirement 7: Container Build Documentation

**User Story:** As a developer, I want clear build and run instructions, so that I can build the container locally and integrate it into CI/CD pipelines.

#### Acceptance Criteria

1. THE `cicd-runner/README.md` SHALL include a section documenting how to build the Docker image using `docker build`
2. THE `cicd-runner/README.md` SHALL include a section documenting how to run the container with required environment variables and CLI arguments
3. THE `cicd-runner/README.md` SHALL include example commands for GitHub Actions, GitLab CI, and Jenkins integration
4. THE `cicd-runner/README.md` SHALL document all required and optional environment variables
5. THE `cicd-runner/README.md` SHALL document minimum resource requirements for the container (memory, CPU)

### Requirement 8: Dockerignore Configuration

**User Story:** As a developer, I want a `.dockerignore` file, so that unnecessary files are excluded from the Docker build context and the build is fast.

#### Acceptance Criteria

1. THE `.dockerignore` file SHALL reside at `cicd-runner/.dockerignore`
2. THE `.dockerignore` file SHALL exclude the `venv/` directory
3. THE `.dockerignore` file SHALL exclude the `__pycache__/` directories
4. THE `.dockerignore` file SHALL exclude the `.pytest_cache/` directory
5. THE `.dockerignore` file SHALL exclude the `.hypothesis/` directory
6. THE `.dockerignore` file SHALL exclude the `htmlcov/` directory
7. THE `.dockerignore` file SHALL exclude the `tests/` directory
8. THE `.dockerignore` file SHALL exclude the `.env` and `.env.example` files
9. THE `.dockerignore` file SHALL exclude the `.coverage` file
10. THE `.dockerignore` file SHALL exclude the `*.egg-info/` directories

### Requirement 9: Container Health and Validation

**User Story:** As a DevOps engineer, I want to verify the container is correctly built, so that I can trust it will work in my CI/CD pipeline.

#### Acceptance Criteria

1. WHEN the Container is built, THE Playwright_Chromium binary SHALL be executable by the Non_Root_User
2. WHEN the Container is built, THE `cicd-runner` CLI command SHALL be available on the PATH
3. WHEN the Container is run with `--help`, THE Runner SHALL respond with usage information and exit with code 0
4. IF the Playwright_Chromium binary is missing or corrupt, THEN THE Runner SHALL exit with code 2 and log a descriptive error message
