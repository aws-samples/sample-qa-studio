# Implementation Plan: WP3 Agent Skills Improvements

## Overview

Enhance the existing QA Studio CLI agent skills (SKILL.md files and reference files) based on Anthropic best practices, add content validation tests, and verify the already-implemented skills manager copy behavior. All work targets markdown skill files and the Python test suite — no new modules or CLI commands.

## Tasks

- [x] 1. Enhance `qa-studio-tests` SKILL.md
  - [x] 1.1 Update frontmatter description with trigger keywords
    - Add "UI automation", "browser testing", "end-to-end tests", "E2E testing", "web application testing", "Nova Act" to the `description` field
    - Retain all existing keywords and negative-scope statements
    - Keep third-person voice
    - _Requirements: 1.1, 1.3, 1.4_

  - [x] 1.2 Improve prerequisites section with expected output
    - Add expected output for `qa-studio status` showing authenticated state (checkmarks for auth and skills) and not-authenticated state
    - Add fallback instruction for running `qa-studio setup` when skills are not installed
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 1.3 Add "Choosing the Right Approach" decision tree section
    - Cover at least three decision points: has clear test description, linear vs complex flow, modifying existing test
    - Map each outcome to specific CLI command or workflow (AI-generated, manual creation, test editing)
    - Include summary of when to use AI-generated vs manual creation
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 1.4 Add "Examples" section with concrete input/output pairs
    - At least 3 examples with full CLI commands and expected output descriptions
    - Include `--from-journey` example with realistic journey description and expected output
    - Include local execution example with `--base-url` and `--var` flags
    - Use generic placeholder values (e.g., `app.example.com`, `demo@example.com`)
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

  - [x] 1.5 Add "Test Creation Workflow" feedback loop section
    - Document iterative loop: create → review → test → evaluate → refine → deploy
    - Include tips for refining journey descriptions (be specific about button text, include expected outcomes, mention element types)
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 1.6 Enhance error handling section
    - Document at least 5 error scenarios with exact error message, cause, and recovery command
    - Cover: authentication failure, test not found, execution failure, Nova Act region error, journey generation producing incorrect steps
    - Provide actionable refinement tips for journey generation issues
    - _Requirements: 6.1, 6.2, 6.5_

  - [x] 1.7 Verify SKILL.md stays under 500 lines; extract to reference files if needed
    - Count total lines after all additions
    - If over 500 lines, move appropriate sections to `reference/` subdirectory with links from main file
    - _Requirements: 10.1, 10.3_

- [x] 2. Enhance `qa-studio-suites` SKILL.md
  - [x] 2.1 Update frontmatter description with trigger keywords
    - Add "batch testing", "regression suite", "CI/CD tests" to the `description` field
    - Retain all existing keywords and negative-scope statements
    - Keep third-person voice
    - _Requirements: 1.2, 1.3, 1.4_

  - [x] 2.2 Improve prerequisites section with expected output
    - Add expected output for `qa-studio status` showing authenticated and not-authenticated states
    - Add fallback instruction for `qa-studio setup`
    - _Requirements: 5.4_

  - [x] 2.3 Add "Examples" section with concrete input/output pairs
    - At least 2 examples with full CLI commands and expected output descriptions
    - Use generic placeholder values
    - _Requirements: 2.4, 2.5_

  - [x] 2.4 Enhance error handling section
    - Document at least 4 error scenarios with exact error message, cause, and recovery command
    - Cover: authentication failure, suite not found, test not found when adding, invalid cron expression
    - _Requirements: 6.3, 6.4_

  - [x] 2.5 Verify SKILL.md stays under 500 lines
    - _Requirements: 10.2, 10.3_

- [x] 3. Checkpoint — Review skill content
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Update reference file tables of contents
  - [x] 4.1 Replace `step-types.md` TOC with descriptive entries
    - Each entry should include step type name and brief purpose description for all 7 step types
    - Use markdown anchor links to each section
    - TOC must be within the first 15 lines
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 4.2 Verify and enhance `validation-operators.md` TOC
    - Confirm TOC is grouped by operator category (string, number, boolean)
    - Ensure descriptive entries with anchor links
    - TOC must be within the first 15 lines
    - _Requirements: 7.1, 7.2, 7.4_

- [x] 5. Add validation checklist
  - [x] 5.1 Add validation checklist content
    - Include SKILL_File quality checks (frontmatter, description, trigger keywords, line limit, examples, prerequisites, error handling, feedback loop)
    - Include progressive disclosure checks (concise main file, reference files, links, TOCs, decision tree)
    - Include Kiro integration checks (discoverability, CLI commands, examples syntax, common issues, file copies)
    - Add as a section in `qa-studio-tests` SKILL.md or as a separate reference file if line budget requires it
    - _Requirements: 9.1, 9.2, 9.3_

- [x] 6. Create content validation test suite
  - [x] 6.1 Create `tests/test_skill_content.py` with frontmatter keyword tests
    - Validate `qa-studio-tests` description contains all required trigger keywords
    - Validate `qa-studio-suites` description contains all required trigger keywords
    - Validate existing keywords are retained
    - _Requirements: 11.1_

  - [x] 6.2 Add section existence tests
    - Validate `qa-studio-tests` contains "Examples", "Choosing the Right Approach", "Test Creation Workflow" sections
    - Validate `qa-studio-suites` contains "Examples" section
    - Validate example counts (≥3 for tests, ≥2 for suites)
    - _Requirements: 11.2_

  - [x] 6.3 Add error handling content tests
    - Validate `qa-studio-tests` error handling has ≥5 scenarios covering auth failure, test not found, execution failure, Nova Act region, journey generation
    - Validate `qa-studio-suites` error handling has ≥4 scenarios covering auth failure, suite not found, test not found, invalid cron
    - _Requirements: 11.2_

  - [x] 6.4 Add reference file TOC tests
    - Validate all reference files >100 lines have a TOC with anchor links in the first 15 lines
    - Validate `step-types.md` TOC has descriptive entries for all 7 step types
    - Validate `validation-operators.md` TOC is grouped by category
    - _Requirements: 11.6_

  - [x] 6.5 Add SKILL.md line limit tests
    - Validate all SKILL.md files are under 500 lines
    - _Requirements: 11.2_

  - [ ]* 6.6 Write property test for frontmatter trigger keywords
    - **Property 1: Frontmatter contains all required trigger keywords**
    - **Validates: Requirements 1.1, 1.2, 1.3**

  - [ ]* 6.7 Write property test for reference file TOC presence
    - **Property 2: Reference files over 100 lines have a TOC with anchor links in the first 15 lines**
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 6.8 Write property test for SKILL.md line limit
    - **Property 8: SKILL.md files under 500 lines**
    - **Validates: Requirements 10.1, 10.2**

- [x] 7. Add skills manager copy-specific tests
  - [x] 7.1 Add install creates real directories test
    - Assert `install_skills()` creates real directories (not symlinks) with explicit `not .is_symlink()` check
    - Assert SKILL.md and reference subdirectories are copied
    - _Requirements: 11.3, 11.4_

  - [x] 7.2 Add uninstall removes copies and cleans symlinks test
    - Assert `uninstall_skills()` removes copied directories
    - Assert stale symlinks from previous versions are cleaned up
    - _Requirements: 11.5_

  - [ ]* 7.3 Write property test for install creates real directories
    - **Property 3: Install creates real directories, not symlinks**
    - **Validates: Requirements 8.1, 8.2, 8.3**

  - [ ]* 7.4 Write property test for status check correctness
    - **Property 4: Status check reflects filesystem state**
    - **Validates: Requirements 8.3**

  - [ ]* 7.5 Write property test for uninstall removes skills and symlinks
    - **Property 5: Uninstall removes installed skills and stale symlinks**
    - **Validates: Requirements 8.4, 8.5**

  - [ ]* 7.6 Write property test for uninstall preserves non-skill paths
    - **Property 6: Uninstall preserves non-skill paths**
    - **Validates: Requirements 8.6**

  - [ ]* 7.7 Write property test for install/uninstall round-trip
    - **Property 7: Install then uninstall round-trip**
    - **Validates: Requirements 8.1, 8.4**

- [x] 8. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- The skills manager code change (symlinks → copies) is already implemented — tasks 7.x only add test coverage
- No new Python modules or CLI commands are introduced
- All SKILL.md content must stay under 500 lines; overflow goes to `reference/` files
- Property tests use Hypothesis library (already in dev dependencies)
- Existing test fixtures (`tmp_kiro_dir`, `tmp_skills_source`) in `conftest.py` are reused
