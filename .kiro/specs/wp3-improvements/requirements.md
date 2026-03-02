# Requirements Document

## Introduction

Improve the existing WP3 Agent Skills for the QA Studio CLI based on Anthropic best practices for Agent Skills authoring. The improvements enhance skill discoverability, provide concrete examples with input/output pairs, add decision trees for choosing approaches, document iterative test creation workflows, improve error handling guidance, and fix a critical infrastructure issue where the skills manager used symlinks (which Kiro cannot follow) by switching to file copies.

## Glossary

- **SKILL_File**: The main markdown file (`SKILL.md`) in each skill directory, containing YAML frontmatter (name, description) and concise usage instructions
- **Reference_File**: A supplementary markdown file in a skill's `reference/` subdirectory providing detailed content on a specific topic
- **Skills_Manager**: The module at `qa_studio_cli/skills/manager.py` responsible for installing, uninstalling, and checking the status of skills
- **Kiro_Skills_Directory**: The directory `~/.kiro/skills/` where Kiro IDE discovers installed skills
- **Frontmatter**: YAML metadata block at the top of a SKILL_File delimited by `---` lines, containing `name` and `description` fields
- **Decision_Tree**: A structured guide within a SKILL_File that helps the Kiro agent choose the correct approach based on the developer's intent
- **Feedback_Loop**: A documented iterative workflow for creating, testing, refining, and deploying tests

## Requirements

### Requirement 1: Enhanced SKILL.md Description Fields

**User Story:** As the Kiro AI agent, I want SKILL_File descriptions to include more specific trigger keywords and technology terms, so that I can discover the correct skill for a wider range of developer requests.

#### Acceptance Criteria

1. THE SKILL_File for `qa-studio-tests` SHALL include the following additional trigger keywords in the `description` frontmatter field: "UI automation", "browser testing", "end-to-end tests", "E2E testing", "web application testing", "Nova Act"
2. THE SKILL_File for `qa-studio-suites` SHALL include the following additional trigger keywords in the `description` frontmatter field: "batch testing", "regression suite", "CI/CD tests"
3. THE SKILL_File descriptions SHALL retain all existing trigger keywords and negative-scope statements already present
4. THE SKILL_File descriptions SHALL remain written in third person

### Requirement 2: Concrete Examples Section

**User Story:** As the Kiro AI agent, I want concrete input/output examples in the SKILL_File, so that I can produce accurate CLI commands by following demonstrated patterns rather than inferring syntax.

#### Acceptance Criteria

1. THE SKILL_File for `qa-studio-tests` SHALL contain an "Examples" section with at least three concrete examples showing full CLI commands and their expected output
2. WHEN an example demonstrates `--from-journey` test creation, THE example SHALL include a realistic journey description, the full CLI command, and a description of the expected output
3. WHEN an example demonstrates local test execution, THE example SHALL include `--base-url` and `--var` flags with realistic placeholder values and a description of the expected output
4. THE SKILL_File for `qa-studio-suites` SHALL contain an "Examples" section with at least two concrete examples showing full CLI commands and their expected output
5. THE examples SHALL use realistic but generic placeholder values (e.g., `app.example.com`, `demo@example.com`) and SHALL NOT contain real user data

### Requirement 3: Conditional Workflow Patterns

**User Story:** As the Kiro AI agent, I want a decision tree in the SKILL_File, so that I can choose the correct test creation approach based on the developer's intent without asking unnecessary clarifying questions.

#### Acceptance Criteria

1. THE SKILL_File for `qa-studio-tests` SHALL contain a "Choosing the Right Approach" section with a structured decision tree
2. THE Decision_Tree SHALL cover at least three decision points: whether the developer has a clear test description, whether the flow is linear or complex, and whether the developer needs to modify an existing test
3. THE Decision_Tree SHALL map each decision outcome to a specific CLI command or workflow (AI-generated creation, manual creation, or test editing)
4. THE Decision_Tree SHALL include a summary of when to use AI-generated creation versus manual creation

### Requirement 4: Feedback Loop for Iterative Test Creation

**User Story:** As the Kiro AI agent, I want a documented iterative workflow for test creation, so that I can guide developers through creating, testing, refining, and deploying tests in a structured loop.

#### Acceptance Criteria

1. THE SKILL_File for `qa-studio-tests` SHALL contain a "Test Creation Workflow" section documenting an iterative feedback loop
2. THE Feedback_Loop SHALL include the following ordered steps: create test, review generated steps, test locally, evaluate results, refine if needed, repeat until passing, deploy
3. THE Feedback_Loop SHALL include tips for refining journey descriptions when AI-generated tests produce incorrect steps
4. THE Feedback_Loop tips SHALL advise being specific about button text, including expected outcomes, and mentioning element types

### Requirement 5: Improved Prerequisites Section

**User Story:** As the Kiro AI agent, I want the prerequisites section to show expected command output, so that I can verify the CLI state before attempting operations and provide accurate troubleshooting guidance.

#### Acceptance Criteria

1. THE SKILL_File for `qa-studio-tests` SHALL include expected output examples for the `qa-studio status` command in the prerequisites section
2. THE expected output SHALL show both the authenticated state (with checkmark indicators for authentication and skills) and the not-authenticated state
3. THE SKILL_File for `qa-studio-tests` SHALL include a fallback instruction for running `qa-studio setup` when skills are not installed
4. THE SKILL_File for `qa-studio-suites` SHALL include the same prerequisites improvements as the `qa-studio-tests` SKILL_File

### Requirement 6: Enhanced Error Handling Sections

**User Story:** As the Kiro AI agent, I want comprehensive error handling guidance with specific error messages and recovery commands, so that I can help developers resolve issues without escalation.

#### Acceptance Criteria

1. THE SKILL_File for `qa-studio-tests` SHALL document at least five common error scenarios with the exact error message, the cause, and the recovery command
2. THE error scenarios for `qa-studio-tests` SHALL include: authentication failure, test not found, execution failure, Nova Act region error, and journey generation producing incorrect steps
3. THE SKILL_File for `qa-studio-suites` SHALL document at least four common error scenarios with the exact error message, the cause, and the recovery command
4. THE error scenarios for `qa-studio-suites` SHALL include: authentication failure, suite not found, test not found when adding to suite, and invalid cron expression
5. WHEN documenting the "journey generation produces incorrect steps" error scenario, THE SKILL_File SHALL provide actionable refinement tips rather than generic advice

### Requirement 7: Reference File Table of Contents

**User Story:** As the Kiro AI agent, I want reference files to have a table of contents, so that I can quickly locate specific sections without reading the entire file.

#### Acceptance Criteria

1. WHEN a Reference_File exceeds 100 lines, THE Reference_File SHALL include a table of contents within the first 15 lines
2. THE table of contents SHALL use markdown anchor links to each major section in the file
3. THE Reference_File `step-types.md` SHALL include a table of contents with descriptive entries (step type name and brief purpose) for each of the seven step types
4. THE Reference_File `validation-operators.md` SHALL include a table of contents grouped by operator category (string, number, boolean)

### Requirement 8: Skills Manager File Copy Instead of Symlinks

**User Story:** As a developer, I want the skills manager to copy skill files instead of creating symlinks, so that Kiro IDE can read the skill content (Kiro does not follow symlinks).

#### Acceptance Criteria

1. THE Skills_Manager SHALL use `shutil.copytree` to copy skill directories from the bundled skills directory into the Kiro_Skills_Directory
2. THE Skills_Manager SHALL NOT create symlinks for skill installation
3. WHEN checking if a skill is already installed, THE Skills_Manager SHALL verify that a directory exists at the target path containing a `SKILL.md` file
4. WHEN uninstalling skills, THE Skills_Manager SHALL use `shutil.rmtree` to remove copied skill directories that contain a `SKILL.md` file
5. WHEN uninstalling skills, THE Skills_Manager SHALL also clean up stale symlinks from previous versions that used symlink-based installation
6. THE Skills_Manager SHALL preserve the existing behavior of skipping paths that are not valid skills (no `SKILL.md` present and not a symlink)

### Requirement 9: Validation Checklist Update

**User Story:** As a developer maintaining the skills, I want an updated validation checklist that covers all the new quality criteria, so that future skill changes can be verified against a comprehensive standard.

#### Acceptance Criteria

1. THE SKILL_File quality checklist SHALL include checks for: valid YAML frontmatter, third-person description, trigger keywords in description, main content under 500 lines, concrete examples with input/output, prerequisites section with expected output, error handling guidance, and feedback loop documentation
2. THE progressive disclosure checklist SHALL include checks for: concise main SKILL_File, detailed content in reference files, clear links to reference files, table of contents in reference files exceeding 100 lines, and decision tree for choosing approaches
3. THE Kiro integration checklist SHALL include checks for: skills discoverable by Kiro, correct CLI commands referenced, examples matching actual CLI syntax, common issues documented, and file copies (not symlinks) used for installation

### Requirement 10: SKILL_File Line Limit Compliance

**User Story:** As a developer, I want all SKILL_Files to remain under 500 lines after improvements, so that token usage stays efficient and the Kiro agent loads skill content quickly.

#### Acceptance Criteria

1. THE SKILL_File for `qa-studio-tests` SHALL remain under 500 lines after all improvements are applied
2. THE SKILL_File for `qa-studio-suites` SHALL remain under 500 lines after all improvements are applied
3. IF adding new sections causes a SKILL_File to exceed 500 lines, THEN the content SHALL be moved to a new Reference_File in the `reference/` subdirectory with a link from the main SKILL_File

### Requirement 11: Testing for Improvements

**User Story:** As a developer, I want tests that verify the improved skill content and updated skills manager behavior, so that regressions are caught automatically.

#### Acceptance Criteria

1. THE test suite SHALL validate that all SKILL_File frontmatter `description` fields contain the required trigger keywords
2. THE test suite SHALL validate that all SKILL_Files contain the required new sections (Examples, Choosing the Right Approach, Test Creation Workflow for qa-studio-tests)
3. THE test suite SHALL validate that the Skills_Manager uses file copies and does not create symlinks
4. THE test suite SHALL validate that `install_skills()` creates real directories (not symlinks) at the target paths
5. THE test suite SHALL validate that `uninstall_skills()` removes copied directories and cleans up stale symlinks
6. THE test suite SHALL validate that all Reference_Files exceeding 100 lines contain a table of contents
