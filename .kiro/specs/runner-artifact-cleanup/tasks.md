# Implementation Plan: Runner Artifact Cleanup

## Overview

Implement a cleanup module that removes execution artifact directories after suite runs complete, and removes stale directories from previous runs. The cleanup is fail-safe and never affects the runner's exit code.

## Tasks

- [ ] 1. Add cleanup_retention_hours to Settings
  - [ ] 1.1 Add `cleanup_retention_hours` field to `Settings` in `qa-studio-ci-runner/src/config/settings.py`
    - Add `cleanup_retention_hours: float = Field(default=24.0, description="Hours to retain old suite directories. 0 disables stale cleanup.")`
    - Load from `CLEANUP_RETENTION_HOURS` env var in `from_env()`
    - _Requirements: 2.3_
  - [ ]* 1.2 Write unit tests for the new Settings field
    - Test default value is 24.0 when env var is not set
    - Test custom value is loaded from env var
    - Test zero value is accepted
    - _Requirements: 2.3_

- [ ] 2. Implement Cleanup class
  - [ ] 2.1 Create `qa-studio-ci-runner/src/execution/cleanup.py` with `CleanupResult` dataclass and `Cleanup` class
    - Implement `CleanupResult` dataclass with `removed_dirs`, `removed_files`, `errors` fields
    - Implement `__init__(self, base_path: Path)`
    - Implement `remove_suite_directory(self, suite_execution_id: str) -> CleanupResult`
      - Use `shutil.rmtree` with `onerror` handler for permission errors
      - Count files and dirs before removal
      - Handle missing directory gracefully
      - Log count of removed items
    - Implement `remove_stale_directories(self, retention_seconds: float) -> CleanupResult`
      - Scan base_path for directories with mtime older than threshold
      - Remove each stale directory using same rmtree approach
      - Handle missing base_path gracefully
      - Log count of removed items
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.5_

  - [ ]* 2.2 Write property test: Recursive removal leaves no trace
    - **Property 1: Recursive removal leaves no trace**
    - Generate random directory trees, call remove_suite_directory, assert directory is gone
    - **Validates: Requirements 1.1, 1.2**

  - [ ]* 2.3 Write property test: Cleanup result counts match actual removals
    - **Property 2: Cleanup result counts match actual removals**
    - Generate random directory trees, count items, call remove_suite_directory, assert counts match
    - **Validates: Requirements 1.5**

  - [ ]* 2.4 Write property test: Stale-only removal preserves young directories
    - **Property 3: Stale-only removal preserves young directories**
    - Generate directories with varying ages, call remove_stale_directories, assert only stale ones removed
    - **Validates: Requirements 2.1, 2.2**

  - [ ]* 2.5 Write unit tests for Cleanup edge cases
    - Test remove_suite_directory with non-existent directory
    - Test remove_stale_directories with non-existent base path
    - Test remove_stale_directories with zero retention (skip behavior)
    - Test permission error handling (read-only file)
    - _Requirements: 1.3, 1.4, 2.4, 2.5_

- [ ] 3. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Integrate cleanup into main.py
  - [ ] 4.1 Call Cleanup from `run_runner()` after summary is printed and exit code is determined
    - Import Cleanup class
    - After `exit_code = determine_exit_code(results)`, add cleanup calls wrapped in try/except
    - Call `remove_suite_directory(suite_execution_id)`
    - If `settings.cleanup_retention_hours > 0`, call `remove_stale_directories()`
    - Catch all exceptions, log as warning, do not modify exit_code
    - _Requirements: 3.1, 3.2_

  - [ ]* 4.2 Write property test: Cleanup errors do not affect exit code
    - **Property 4: Cleanup errors do not affect exit code**
    - Generate random exit codes and exception types, mock cleanup to raise, assert exit code unchanged
    - **Validates: Requirements 3.1**

  - [ ]* 4.3 Write unit test for cleanup integration in main.py
    - Test that cleanup is called after summary
    - Test that cleanup exception does not change exit code
    - _Requirements: 3.1, 3.2_

- [ ] 5. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All tests go in `qa-studio-ci-runner/tests/test_cleanup.py`
- Property tests use `hypothesis` (already in `requirements-dev.txt`)
- The Cleanup class is intentionally simple — no background threads, no async, just synchronous file operations
