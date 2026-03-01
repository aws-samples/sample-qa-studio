# Requirements Document

## Introduction

The CI/CD runner creates execution artifacts under `~/.ci_runner/{suite_execution_id}/{execution_id}/` with subdirectories for `artifacts/`, `nova_act_logs/`, and `downloads/`. These directories accumulate over time and are never fully cleaned up, leading to unbounded disk usage. This feature adds a cleanup mechanism that removes execution artifacts after a suite run completes and all artifacts have been uploaded.

## Glossary

- **Runner**: The CI/CD runner application (`qa-studio-ci-runner/`) that executes test suites
- **Cleanup_Module**: The module responsible for removing execution artifact directories from disk
- **Execution_Directory**: A directory at `~/.ci_runner/{suite_execution_id}/{execution_id}/` containing artifacts, logs, and downloads for a single usecase execution
- **Suite_Directory**: A directory at `~/.ci_runner/{suite_execution_id}/` containing all execution directories for a single suite run
- **Base_Directory**: The root directory `~/.ci_runner/` under which all suite directories are created
- **Retention_Period**: A configurable duration after which old suite directories become eligible for removal
- **Settings**: The application settings model loaded from environment variables

## Requirements

### Requirement 1: Clean up current suite execution directory after run completes

**User Story:** As a CI/CD operator, I want the runner to clean up the current suite's execution directories after a run completes, so that disk space is reclaimed immediately.

#### Acceptance Criteria

1. WHEN a suite execution completes (all usecases finished and artifacts uploaded), THE Cleanup_Module SHALL remove the Suite_Directory for that execution
2. WHEN removing the Suite_Directory, THE Cleanup_Module SHALL remove all subdirectories and files within the Suite_Directory recursively
3. IF the Suite_Directory does not exist at cleanup time, THEN THE Cleanup_Module SHALL handle the missing directory gracefully without raising an error
4. IF a file or directory cannot be removed due to a permission error, THEN THE Cleanup_Module SHALL log a warning and continue without failing the runner process
5. WHEN cleanup completes, THE Cleanup_Module SHALL log the number of files and directories removed

### Requirement 2: Clean up stale suite directories from previous runs

**User Story:** As a CI/CD operator, I want the runner to remove old artifact directories from previous runs, so that disk space does not grow unbounded over time.

#### Acceptance Criteria

1. WHEN the runner starts a new suite execution, THE Cleanup_Module SHALL scan the Base_Directory for Suite_Directories older than the Retention_Period
2. WHEN a Suite_Directory modification time is older than the Retention_Period, THE Cleanup_Module SHALL remove that Suite_Directory and all its contents
3. THE Settings SHALL include a configurable Retention_Period with a default value of 24 hours
4. WHEN the Retention_Period is set to zero, THE Cleanup_Module SHALL skip stale directory cleanup entirely
5. IF the Base_Directory does not exist, THEN THE Cleanup_Module SHALL skip stale cleanup without raising an error

### Requirement 3: Cleanup must not affect runner exit behavior

**User Story:** As a CI/CD operator, I want cleanup failures to never change the runner's exit code, so that test results remain the source of truth for pipeline success or failure.

#### Acceptance Criteria

1. IF any error occurs during cleanup, THEN THE Runner SHALL catch the error, log it as a warning, and proceed with the normal exit code based on test results
2. THE Cleanup_Module SHALL execute cleanup after the execution summary has been printed and the exit code has been determined
3. WHEN cleanup is invoked, THE Cleanup_Module SHALL accept a base path parameter so that the cleanup target is explicit and testable
