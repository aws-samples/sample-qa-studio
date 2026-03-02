# Implementation Plan: WP3 Agent Skills

## Overview

Implement Kiro IDE Agent Skills for the QA Studio CLI: two skill directories with markdown instruction files, a Skills_Manager module for symlink-based installation, Pydantic data models, and three CLI commands (`setup`, `uninstall`, enhanced `status`). Tasks are ordered by dependency: Pydantic models → Skills_Manager module → skill content files → CLI commands → setup.py packaging → tests → final validation.

## Tasks

- [x] 1. Create Pydantic data models for skills
  - [x] 1.1 Create `qa-studio-cli/qa_studio_cli/models/skills.py`
    - Define `SkillInfo(BaseModel)` with fields: `name` (str), `path` (Path); set `arbitrary_types_allowed = True`
    - Define `SkillState(str, Enum)` with values: `INSTALLED`, `NOT_INSTALLED`, `CONFLICT`, `INSTALL_FAILED`, `REMOVED`, `SKIPPED`
    - Define `SkillStatus(BaseModel)` with fields: `name` (str), `state` (SkillState), `message` (str, default "")
    - Define `SkillFrontmatter(BaseModel)` with fields: `name` (str, min_length=1), `description` (str, min_length=1)
    - _Requirements: 8.4, 10.6_

  - [x] 1.2 Update `qa-studio-cli/qa_studio_cli/models/__init__.py`
    - Export `SkillInfo`, `SkillState`, `SkillStatus`, `SkillFrontmatter`
    - _Requirements: 8.4_

  - [ ]* 1.3 Write unit tests for skill models (`qa-studio-cli/tests/test_skill_models.py`)
    - Test `SkillInfo` accepts Path objects
    - Test `SkillStatus` defaults message to empty string
    - Test `SkillFrontmatter` rejects empty name or description
    - Test `SkillState` enum values match expected strings
    - _Requirements: 10.6_

- [x] 2. Implement Skills_Manager module
  - [x] 2.1 Create `qa-studio-cli/qa_studio_cli/skills/__init__.py`
    - Empty init file to make skills a Python package
    - _Requirements: 8.1_

  - [x] 2.2 Create `qa-studio-cli/qa_studio_cli/skills/manager.py`
    - Define module-level constants: `KIRO_DIR = Path.home() / ".kiro"`, `KIRO_SKILLS_DIR = KIRO_DIR / "skills"`
    - Implement `get_skills_directory() -> Path`: resolve bundled `skills/` directory via `Path(__file__).resolve().parent.parent.parent / "skills"`
    - Implement `list_available_skills() -> list[SkillInfo]`: scan skills directory for subdirectories containing `SKILL.md`, return sorted list of `SkillInfo`
    - Implement `is_kiro_installed() -> bool`: check `KIRO_DIR.is_dir()`
    - Implement `check_skill_status(skill: SkillInfo) -> SkillStatus`: return INSTALLED if valid symlink at target, CONFLICT if path exists but not symlink, NOT_INSTALLED if path doesn't exist
    - Implement `check_all_skills_status() -> list[SkillStatus]`: call `check_skill_status` for each available skill
    - Implement `install_skills() -> list[SkillStatus]`: check Kiro dir exists, create skills dir, create symlinks per skill, handle already-installed/conflict/OS-error cases, return status list
    - Implement `uninstall_skills() -> list[SkillStatus]`: iterate skills, remove symlinks only (skip non-symlinks), return status list
    - Use `pathlib.Path` exclusively for all filesystem operations
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ]* 2.3 Write unit tests for Skills_Manager (`qa-studio-cli/tests/test_skills_manager.py`)
    - Test `get_skills_directory()` returns existing path
    - Test `list_available_skills()` returns correct skills from bundled directory
    - Test `list_available_skills()` ignores directories without SKILL.md
    - Test `check_skill_status()` returns INSTALLED for valid symlink
    - Test `check_skill_status()` returns NOT_INSTALLED for missing path
    - Test `check_skill_status()` returns CONFLICT for regular directory
    - Test `install_skills()` creates `~/.kiro/skills/` directory
    - Test `install_skills()` skips already-installed skills
    - Test `install_skills()` warns on conflict paths
    - Test `install_skills()` handles OS errors gracefully per-skill
    - Test `install_skills()` returns empty list when `~/.kiro/` missing
    - Test `uninstall_skills()` removes only symlinks
    - Test `uninstall_skills()` skips non-symlink paths
    - Test `uninstall_skills()` handles no-skills-to-remove scenario
    - Test `is_kiro_installed()` returns True/False based on `~/.kiro/` existence
    - Use `tmp_path` and `monkeypatch` to avoid touching real `~/.kiro/`
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ]* 2.4 Write property test: Install creates correct symlinks (Property 3)
    - **Property 3: Install creates correct symlinks for all skills**
    - For any set of skill directories containing SKILL.md, after `install_skills()` with valid `~/.kiro/`, each skill has a symlink at the correct target
    - Use Hypothesis with random skill names, temp directories
    - **Validates: Requirements 5.3, 5.4, 8.5**

  - [ ]* 2.5 Write property test: Install is idempotent (Property 4)
    - **Property 4: Install is idempotent**
    - For any state where all skills are already installed, calling `install_skills()` again does not modify symlinks and reports all as already installed
    - **Validates: Requirements 5.5**

  - [ ]* 2.6 Write property test: Uninstall removes all symlinks (Property 5)
    - **Property 5: Uninstall removes all skill symlinks**
    - For any set of installed skill symlinks, after `uninstall_skills()`, none of those symlink paths exist
    - **Validates: Requirements 6.2, 8.6**

  - [ ]* 2.7 Write property test: Uninstall preserves non-symlinks (Property 6)
    - **Property 6: Uninstall preserves non-symlink paths**
    - For any path at target that is a regular file or directory, `uninstall_skills()` leaves it unchanged
    - **Validates: Requirements 6.5**

  - [ ]* 2.8 Write property test: Install/uninstall round-trip (Property 7)
    - **Property 7: Install then uninstall round-trip**
    - For any valid `~/.kiro/`, calling `install_skills()` then `uninstall_skills()` results in no skill symlinks remaining
    - **Validates: Requirements 5.4, 6.2**

  - [ ]* 2.9 Write property test: Skill discovery matches directory structure (Property 8)
    - **Property 8: Skill discovery matches directory structure**
    - For any skills directory with N subdirectories containing SKILL.md, `list_available_skills()` returns exactly N items with matching names
    - **Validates: Requirements 8.3**

  - [ ]* 2.10 Write property test: Status check reflects filesystem state (Property 9)
    - **Property 9: Status check reflects filesystem state**
    - For any filesystem state (valid symlink, non-symlink path, non-existent), `check_skill_status()` returns the correct `SkillState`
    - **Validates: Requirements 8.4**

- [x] 3. Checkpoint - Ensure models and manager tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Create skill content files
  - [x] 4.1 Create `qa-studio-cli/skills/qa-studio-tests/SKILL.md`
    - Add YAML frontmatter with `name: qa-studio-tests` and third-person `description` including trigger keywords (create test, run test, QA, UI test, verify functionality) and negative cases (not for unit/integration/API tests)
    - Add sections: Prerequisites (check auth via `qa-studio status`), Creating Tests (AI-generated and manual), Executing Tests Locally, Managing Tests, Error Handling/Troubleshooting
    - Include concrete CLI command examples with realistic placeholder values
    - Link to `reference/step-types.md`, `reference/validation-operators.md`, `reference/manual-creation.md` using relative paths with forward slashes
    - Keep under 500 lines; only QA Studio-specific knowledge
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 9.1, 9.2, 9.3, 9.4, 9.6, 9.7, 9.8_

  - [x] 4.2 Create `qa-studio-cli/skills/qa-studio-tests/reference/step-types.md`
    - Document all 7 step types: navigation, url, secret, validation, retrieve_value, assertion, download
    - For each: description, required fields, example commands, when-to-use guidance
    - Include table of contents if file exceeds 100 lines
    - Use consistent formatting per requirement 9.5
    - _Requirements: 2.1, 2.4, 9.5_

  - [x] 4.3 Create `qa-studio-cli/skills/qa-studio-tests/reference/validation-operators.md`
    - Document string operators: exact, exact_case_insensitive, contains, contains_case_insensitive, not_equal
    - Document number operators: equals, less_then, greater_then, greater_or_equal_then, less_or_equal_then
    - Document boolean operator: exact
    - Include examples for each operator
    - Include table of contents if file exceeds 100 lines
    - _Requirements: 2.2, 2.4, 9.5_

  - [x] 4.4 Create `qa-studio-cli/skills/qa-studio-tests/reference/manual-creation.md`
    - Step-by-step guide: create blank test, add steps individually, configure variables and secrets, test locally
    - Include table of contents if file exceeds 100 lines
    - _Requirements: 2.3, 2.4, 9.5_

  - [x] 4.5 Create `qa-studio-cli/skills/qa-studio-suites/SKILL.md`
    - Add YAML frontmatter with `name: qa-studio-suites` and third-person `description` including trigger keywords (test suite, group tests, run multiple tests, organize tests) and negative cases (not for creating individual tests)
    - Add sections: Prerequisites (check auth via `qa-studio status`), Creating Suites, Adding Tests to Suites, Executing Suites, Managing Suites, Error Handling/Troubleshooting
    - Include concrete CLI command examples with realistic placeholder values
    - Keep under 500 lines; only QA Studio-specific knowledge
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 9.1, 9.2, 9.3, 9.4, 9.6, 9.7, 9.8_

- [x] 5. Add CLI commands for skill lifecycle
  - [x] 5.1 Add `setup` command to `qa-studio-cli/qa_studio_cli/cli.py`
    - Import Skills_Manager functions
    - Check `is_kiro_installed()` → warn and return if False
    - Call `install_skills()` and display per-skill results with ✓/✗/⚠️ prefixes
    - Show count of installed skills and next-step guidance (`qa-studio login`)
    - Show "all skills already installed" when nothing new installed
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9_

  - [x] 5.2 Add `uninstall` command to `qa-studio-cli/qa_studio_cli/cli.py`
    - Call `uninstall_skills()` and display per-skill results
    - Show count of removed skills or "no skills to remove"
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 5.3 Enhance `status` command in `qa-studio-cli/qa_studio_cli/cli.py`
    - Keep existing auth status display
    - Add "Skills:" section listing each skill with ✓ (installed) or ✗ (not installed) indicator
    - Show guidance to run `qa-studio setup` when any skills are not installed
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 5.4 Write CLI command tests (`qa-studio-cli/tests/test_skills_cli.py`)
    - Test `qa-studio setup` with Kiro installed → installs skills, shows count
    - Test `qa-studio setup` without Kiro → shows warning
    - Test `qa-studio setup` with all skills already installed → shows "already installed"
    - Test `qa-studio uninstall` with installed skills → removes, shows count
    - Test `qa-studio uninstall` with no skills → shows "no skills to remove"
    - Test `qa-studio status` with auth + skills installed → shows ✓ for each skill
    - Test `qa-studio status` with auth + skills not installed → shows ✗ and guidance
    - Test `qa-studio status` without config → shows config error (existing behavior preserved)
    - Use Click's `CliRunner` and `monkeypatch` for filesystem isolation
    - _Requirements: 10.5_

- [x] 6. Checkpoint - Ensure CLI command tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Update package configuration and add content validation tests
  - [x] 7.1 Update `qa-studio-cli/setup.py` to include skills as package data
    - Add `package_data={'': ['skills/**/*.md']}` and `include_package_data=True`
    - Ensure `skills/` directory and all markdown files are distributed with the package
    - _Requirements: 4.4_

  - [x] 7.2 Update test fixtures in `qa-studio-cli/tests/conftest.py`
    - Add `tmp_kiro_dir` fixture: creates temporary `~/.kiro/` directory
    - Add `tmp_skills_source` fixture: creates temporary bundled skills directory with SKILL.md files
    - _Requirements: 10.2, 10.3, 10.4_

  - [ ]* 7.3 Write skill content validation tests (`qa-studio-cli/tests/test_skill_content.py`)
    - Test `qa-studio-tests/SKILL.md` has valid YAML frontmatter with correct name
    - Test `qa-studio-tests/SKILL.md` contains required sections (prerequisites, creating tests, executing, managing, error handling)
    - Test `qa-studio-tests/SKILL.md` contains links to all three reference files
    - Test `qa-studio-tests/SKILL.md` references `qa-studio status` in prerequisites
    - Test `qa-studio-suites/SKILL.md` has valid YAML frontmatter with correct name
    - Test `qa-studio-suites/SKILL.md` contains required sections
    - Test `qa-studio-suites/SKILL.md` references `qa-studio status`
    - Test `step-types.md` documents all 7 step types
    - Test `validation-operators.md` documents all operators
    - Test `manual-creation.md` contains step-by-step guide sections
    - _Requirements: 10.6_

  - [ ]* 7.4 Write property test: SKILL.md files under 500 lines (Property 1)
    - **Property 1: SKILL.md files stay under 500 lines**
    - For any SKILL.md file in the bundled skills directory, the file contains fewer than 500 lines
    - **Validates: Requirements 1.5, 10.7**

  - [ ]* 7.5 Write property test: Reference files TOC (Property 2)
    - **Property 2: Reference files over 100 lines include a table of contents**
    - For any reference file exceeding 100 lines, a table of contents section exists within the first 10 lines
    - **Validates: Requirements 2.4**

  - [ ]* 7.6 Write property test: No backslashes in paths (Property 10)
    - **Property 10: No backslashes in skill file paths**
    - For any markdown file in the bundled skills directory, the content contains no backslash characters in file paths or relative links
    - **Validates: Requirements 9.6**

  - [ ]* 7.7 Write property test: Valid YAML frontmatter (Property 11)
    - **Property 11: All SKILL.md files have valid YAML frontmatter**
    - For any SKILL.md file, parsing YAML frontmatter produces a valid object with non-empty `name` and `description` fields
    - **Validates: Requirements 10.6**

- [x] 8. Final checkpoint - Ensure all tests pass and coverage ≥70%
  - Ensure all tests pass, ask the user if questions arise.
  - Run `pytest --cov=qa_studio_cli tests/` in `qa-studio-cli/` and verify ≥70% coverage for `skills/manager.py`, CLI commands, and `models/skills.py`
  - _Requirements: 10.1_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All data models use Pydantic v2, consistent with existing codebase
- All filesystem tests use `tmp_path` and `monkeypatch` to avoid touching real `~/.kiro/`
- Skill content files use only forward slashes in paths and relative links
- The `skills/` directory is not a Python package — it contains markdown files only
- CLI commands follow existing patterns: Click decorators, ✓/✗ output prefixes
