# Implementation Plan: Rename cicd-runner to qa-studio-ci-runner

## Overview

Pure rename/refactor of the `cicd-runner` package to `qa-studio-ci-runner`. No functional changes — only directory rename, package metadata updates, documentation text replacements, spec file updates, and egg-info cleanup. Internal Python imports (`from src.*`) remain unchanged.

## Tasks

- [x] 1. Rename root directory and clean up egg-info
  - [x] 1.1 Rename `cicd-runner/` directory to `qa-studio-ci-runner/`
    - Use `git mv cicd-runner qa-studio-ci-runner` to preserve git history
    - Verify internal directory structure (`src/`, `tests/`, `Dockerfile`, `setup.py`, `README.md`) is intact after rename
    - _Requirements: 1.1, 1.2_

  - [x] 1.2 Delete `cicd_runner.egg-info/` directory
    - Remove `cicd-runner/cicd_runner.egg-info/` (or `qa-studio-ci-runner/cicd_runner.egg-info/` after rename)
    - It will be regenerated as `qa_studio_ci_runner.egg-info/` on next `pip install -e .`
    - _Requirements: 7.1_

- [x] 2. Update package metadata and Dockerfile
  - [x] 2.1 Update `qa-studio-ci-runner/setup.py`
    - Change `name` from `cicd-runner` to `qa-studio-ci-runner`
    - Change `author` from `CI/CD Runner Team` to `QA Studio Team`
    - Change `description` to reference `QA Studio CI Runner` instead of `CI/CD runner`
    - Change console_scripts entry point from `cicd-runner=src.cli.parser:main` to `qa-studio-ci-runner=src.cli.parser:main`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 2.2 Update `qa-studio-ci-runner/Dockerfile`
    - Change ENTRYPOINT from `/app/.venv/bin/cicd-runner` to `/app/.venv/bin/qa-studio-ci-runner`
    - Update PATH comment from `cicd-runner` to `qa-studio-ci-runner`
    - _Requirements: 3.1, 3.2, 3.3_

- [x] 3. Update documentation files
  - [x] 3.1 Update `qa-studio-ci-runner/README.md`
    - Replace all occurrences of `cicd-runner` with `qa-studio-ci-runner`
    - _Requirements: 4.1_

  - [x] 3.2 Update `docs/cli-reference.md`
    - Replace all command-line references from `cicd-runner` to `qa-studio-ci-runner`
    - Resolve any existing git conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) before or during the rename
    - _Requirements: 4.2_

  - [x] 3.3 Update `docs/ci-cd-integration/generic-docker.md`
    - Replace `cicd-runner` with `qa-studio-ci-runner`
    - Replace `python -m cicd_runner` with `python -m qa_studio_ci_runner`
    - _Requirements: 4.3_

  - [x] 3.4 Update `docs/configuration.md`
    - Replace any occurrences of `cicd-runner` with `qa-studio-ci-runner` if present
    - _Requirements: 4.4_

- [x] 4. Checkpoint
  - Ensure all changes so far are consistent, ask the user if questions arise.

- [x] 5. Update spec and design files
  - [x] 5.1 Update `.kiro/specs/` files that reference `cicd-runner`
    - Replace all path references from `cicd-runner/` to `qa-studio-ci-runner/`
    - Replace all Python module references from `cicd_runner` to `qa_studio_ci_runner`
    - Replace all command references from `cicd-runner` to `qa-studio-ci-runner`
    - Key files: `.kiro/specs/qa-studio-cli/wp1-cli-foundation.md`, `.kiro/specs/runner-log-capture/` contents, `.kiro/specs/wp5-docker-container/` contents, and any others found via grep
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 5.2 Update `.kiro/design/` files that reference `cicd-runner`
    - Replace `python -m cicd_runner` with `python -m qa_studio_ci_runner`
    - Replace any other `cicd-runner` or `cicd_runner` references
    - _Requirements: 5.4, 7.3_

- [x] 6. Verify Python imports are unchanged
  - [x] 6.1 Verify all Python source files under `qa-studio-ci-runner/src/` use `from src.` import paths
    - Grep for any `from cicd_runner` or `from qa_studio_ci_runner` imports — there should be none
    - Confirm all imports use `from src.` pattern
    - _Requirements: 6.1_

  - [x] 6.2 Verify all Python test files under `qa-studio-ci-runner/tests/` use `from src.` import paths
    - Same check as 6.1 but for test files
    - _Requirements: 6.2_

- [x] 7. Checkpoint
  - Ensure all tests pass by running `pytest` from `qa-studio-ci-runner/`, ask the user if questions arise.

- [x] 8. Final verification — no stale references
  - [x] 8.1 Run recursive grep for `cicd-runner` across the repository
    - Exclude `.git/`, `node_modules/`, `venv/`, `__pycache__/`, `*.egg-info/`
    - Must return zero results
    - _Requirements: 8.1_

  - [x] 8.2 Run recursive grep for `cicd_runner` across the repository
    - Exclude `.git/`, `node_modules/`, `venv/`, `__pycache__/`, `*.egg-info/`
    - Must return zero results
    - _Requirements: 8.2_

  - [ ]* 8.3 Write property test for no stale references (Property 1)
    - **Property 1: No stale references in repository**
    - Generate random file paths from the repository file list (excluding build artifacts), read each file, assert neither `cicd-runner` nor `cicd_runner` appears in the content
    - Use Hypothesis with minimum 100 iterations
    - **Validates: Requirements 4.4, 5.1, 5.2, 5.3, 7.3, 8.1, 8.2**

  - [ ]* 8.4 Write property test for Python import paths preserved (Property 2)
    - **Property 2: Python import paths preserved**
    - Generate random Python file paths from `qa-studio-ci-runner/src/` and `qa-studio-ci-runner/tests/`, read each file, extract all import statements, assert none reference `cicd_runner` or `qa_studio_ci_runner` as a top-level module
    - Use Hypothesis with minimum 100 iterations
    - **Validates: Requirements 6.1, 6.2**

  - [x] 8.5 Run full test suite from `qa-studio-ci-runner/`
    - Run `pytest` and verify all existing tests pass with the same results as before the rename
    - _Requirements: 6.3, 8.3_

- [x] 9. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Internal Python imports (`from src.*`) do NOT change — the `src/` package name is unaffected by the directory rename
- The `docs/cli-reference.md` file has existing git conflict markers that must be resolved during task 3.2
- Property tests use Hypothesis (already in use in this project)
- No backend, frontend, API, or DynamoDB changes are needed — this is purely a rename operation
