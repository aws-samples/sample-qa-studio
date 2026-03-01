# Requirements Document

## Introduction

Rename the existing `cicd-runner` package to `qa-studio-ci-runner` across the entire codebase. This covers the root directory, Python module name, setup.py metadata, console script entry point, Dockerfile, all internal imports, test files, documentation, and spec files. The rename aligns branding with the upcoming `qa-studio-cli` tool and is a prerequisite for WP1 of that feature.

## Glossary

- **Runner_Package**: The Python package currently located at `cicd-runner/` in the repository root, distributed as `cicd-runner` via setup.py.
- **Runner_Module**: The Python module namespace used in imports (currently `src.*` within the `cicd-runner/` directory).
- **Console_Script**: The CLI entry point registered in setup.py that allows invoking the runner from the command line.
- **Spec_Files**: Design, requirements, and task documents under `.kiro/specs/` that reference the runner by name.
- **Documentation_Files**: Markdown files under `docs/` and `cicd-runner/README.md` that reference the runner by name or command.

## Requirements

### Requirement 1: Rename Root Directory

**User Story:** As a developer, I want the runner directory to be named `qa-studio-ci-runner/` so that the folder name matches the new branding.

#### Acceptance Criteria

1. WHEN the rename is applied, THE Runner_Package root directory SHALL be located at `qa-studio-ci-runner/` instead of `cicd-runner/`.
2. THE Runner_Package SHALL retain the same internal directory structure (`src/`, `tests/`, `Dockerfile`, `setup.py`, etc.) after the rename.

### Requirement 2: Update setup.py Package Metadata

**User Story:** As a developer, I want setup.py to reflect the new package name so that `pip install` and `pip install -e .` use the correct identifier.

#### Acceptance Criteria

1. THE Runner_Package setup.py `name` field SHALL be `qa-studio-ci-runner`.
2. THE Runner_Package setup.py `author` field SHALL be `QA Studio Team`.
3. THE Runner_Package setup.py `description` field SHALL reference `QA Studio CI Runner` instead of `CI/CD runner`.
4. THE Console_Script entry point SHALL be `qa-studio-ci-runner=src.cli.parser:main`.
5. WHEN a developer runs `pip install -e .` inside `qa-studio-ci-runner/`, THE package SHALL install successfully with the entry point `qa-studio-ci-runner`.

### Requirement 3: Update Dockerfile

**User Story:** As a developer, I want the Dockerfile to reference the new console script name so that the container image works correctly after the rename.

#### Acceptance Criteria

1. THE Dockerfile ENTRYPOINT SHALL reference `/app/.venv/bin/qa-studio-ci-runner`.
2. THE Dockerfile PATH comment SHALL reference `qa-studio-ci-runner` instead of `cicd-runner`.
3. WHEN the Docker image is built from `qa-studio-ci-runner/Dockerfile`, THE container SHALL start the runner via the `qa-studio-ci-runner` entry point.

### Requirement 4: Update Documentation Files

**User Story:** As a developer, I want all documentation to use the new name so that users see consistent branding.

#### Acceptance Criteria

1. THE `qa-studio-ci-runner/README.md` SHALL replace all occurrences of `cicd-runner` with `qa-studio-ci-runner`.
2. THE `docs/cli-reference.md` SHALL replace all command-line references from `cicd-runner` to `qa-studio-ci-runner`.
3. THE `docs/ci-cd-integration/generic-docker.md` SHALL replace `python -m cicd_runner` with `python -m qa_studio_ci_runner` and `cicd-runner` with `qa-studio-ci-runner`.
4. WHEN a user searches for `cicd-runner` or `cicd_runner` in any documentation file, THE search SHALL return zero results.

### Requirement 5: Update Spec and Design Files

**User Story:** As a developer, I want spec files to reference the new name so that future work packages use correct paths and names.

#### Acceptance Criteria

1. THE Spec_Files under `.kiro/specs/` SHALL replace all path references from `cicd-runner/` to `qa-studio-ci-runner/`.
2. THE Spec_Files SHALL replace all Python module references from `cicd_runner` to `qa_studio_ci_runner`.
3. THE Spec_Files SHALL replace all command references from `cicd-runner` to `qa-studio-ci-runner`.
4. THE design document at `.kiro/design/qa-studio-cli.md` SHALL replace `python -m cicd_runner` with `python -m qa_studio_ci_runner`.

### Requirement 6: Update Internal Python Imports

**User Story:** As a developer, I want all Python imports within the runner to remain functional after the rename so that the test suite passes.

#### Acceptance Criteria

1. THE Runner_Module source files under `qa-studio-ci-runner/src/` SHALL use `from src.` import paths (unchanged, since the module uses relative `src.*` imports).
2. THE Runner_Module test files under `qa-studio-ci-runner/tests/` SHALL use `from src.` import paths (unchanged, since tests use relative `src.*` imports).
3. WHEN a developer runs `pytest` from the `qa-studio-ci-runner/` directory, all existing tests SHALL pass.

### Requirement 7: Update External References to the Runner Module

**User Story:** As a developer, I want all references to `python -m cicd_runner` to be updated so that the module can be invoked by its new name.

#### Acceptance Criteria

1. THE `cicd_runner.egg-info/` directory SHALL be removed (it will be regenerated as `qa_studio_ci_runner.egg-info/` on next install).
2. WHEN a developer runs `pip install -e .` and then `qa-studio-ci-runner --help`, THE runner SHALL display help output.
3. THE Spec_Files and design documents SHALL replace `python -m cicd_runner` with `python -m qa_studio_ci_runner` in all code examples and command references.

### Requirement 8: Verify No Stale References Remain

**User Story:** As a developer, I want to confirm that no stale references to the old name exist so that the rename is complete and consistent.

#### Acceptance Criteria

1. WHEN a recursive grep for `cicd-runner` is run across the repository (excluding `.git/`, `node_modules/`, `venv/`, `__pycache__/`, `*.egg-info/`), THE search SHALL return zero results.
2. WHEN a recursive grep for `cicd_runner` is run across the repository (excluding `.git/`, `node_modules/`, `venv/`, `__pycache__/`, `*.egg-info/`), THE search SHALL return zero results.
3. WHEN the full test suite is run from `qa-studio-ci-runner/`, all tests SHALL pass with the same results as before the rename.
