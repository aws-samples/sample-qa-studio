# Requirements Document

## Introduction

Create Kiro IDE Agent Skills for the QA Studio CLI and implement skill lifecycle management commands (`setup`, `uninstall`, enhanced `status`). Agent Skills are markdown-based instruction files that guide the Kiro AI agent on how to use the QA Studio CLI for test creation, execution, and suite management. Skills follow a progressive disclosure pattern with concise main SKILL.md files and detailed reference files. Skills are installed as symlinks from the `qa-studio-cli` package into `~/.kiro/skills/`.

## Glossary

- **Skill**: A directory containing a `SKILL.md` file and optional reference files that instruct the Kiro AI agent on how to use a specific QA Studio CLI capability
- **SKILL_File**: The main markdown file (`SKILL.md`) in each skill directory, containing YAML frontmatter (name, description) and concise usage instructions
- **Reference_File**: A supplementary markdown file in a skill's `reference/` subdirectory providing detailed content on a specific topic (e.g., step types, validation operators)
- **Skills_Directory**: The directory `qa-studio-cli/skills/` within the CLI package that contains all bundled skill directories
- **Kiro_Skills_Directory**: The directory `~/.kiro/skills/` where Kiro IDE discovers installed skills
- **Skills_Manager**: The module responsible for installing, uninstalling, and checking the status of skill symlinks between the Skills_Directory and the Kiro_Skills_Directory
- **Symlink**: A filesystem symbolic link pointing from `~/.kiro/skills/<skill-name>` to the corresponding directory in the CLI package's Skills_Directory
- **CLI**: The `qa-studio-cli` Click-based command-line interface tool
- **Frontmatter**: YAML metadata block at the top of a SKILL_File delimited by `---` lines, containing `name` and `description` fields

## Requirements

### Requirement 1: qa-studio-tests Skill Content

**User Story:** As the Kiro AI agent, I want a skill that teaches me how to create, execute, and manage QA Studio UI tests via the CLI, so that I can assist developers with test automation without requiring them to leave the IDE.

#### Acceptance Criteria

1. THE SKILL_File for `qa-studio-tests` SHALL contain YAML frontmatter with `name` set to `qa-studio-tests` and a `description` written in third person that specifies what the skill does, when to use it (trigger keywords such as "create test", "run test", "QA", "UI test", "verify functionality"), and when NOT to use it (not for unit tests, integration tests, or API tests — only browser-based UI tests)
2. THE SKILL_File for `qa-studio-tests` SHALL contain sections for prerequisites, creating tests (AI-generated and manual), executing tests locally, managing tests, and error handling/troubleshooting (common errors and how to resolve them)
3. THE SKILL_File for `qa-studio-tests` SHALL include concrete CLI command examples with realistic placeholder values for each operation
4. THE SKILL_File for `qa-studio-tests` SHALL link to `reference/step-types.md`, `reference/validation-operators.md`, and `reference/manual-creation.md` using relative paths
5. THE SKILL_File for `qa-studio-tests` SHALL remain under 500 lines to maintain conciseness
6. THE SKILL_File for `qa-studio-tests` SHALL instruct the agent to check authentication via `qa-studio status` before attempting any operation

### Requirement 2: qa-studio-tests Reference Files

**User Story:** As the Kiro AI agent, I want detailed reference documentation on step types, validation operators, and manual test creation, so that I can construct precise test definitions when the developer needs fine-grained control.

#### Acceptance Criteria

1. THE Reference_File `step-types.md` SHALL document all seven step types (navigation, url, secret, validation, retrieve_value, assertion, download) with description, required fields, example commands, and when-to-use guidance for each
2. THE Reference_File `validation-operators.md` SHALL document all string operators (exact, exact_case_insensitive, contains, contains_case_insensitive, not_equal), all number operators (equals, less_then, greater_then, greater_or_equal_then, less_or_equal_then), and the boolean operator (exact) with examples for each
3. THE Reference_File `manual-creation.md` SHALL provide a step-by-step guide covering creating a blank test, adding steps individually, configuring variables and secrets, and testing locally
4. WHEN a Reference_File exceeds 100 lines, THE Reference_File SHALL include a table of contents at the top

### Requirement 3: qa-studio-suites Skill Content

**User Story:** As the Kiro AI agent, I want a skill that teaches me how to manage QA Studio test suites, so that I can help developers group and execute related tests together.

#### Acceptance Criteria

1. THE SKILL_File for `qa-studio-suites` SHALL contain YAML frontmatter with `name` set to `qa-studio-suites` and a `description` written in third person that specifies what the skill does, when to use it (trigger keywords such as "test suite", "group tests", "run multiple tests", "organize tests"), and when NOT to use it (not for creating individual tests — use qa-studio-tests skill instead)
2. THE SKILL_File for `qa-studio-suites` SHALL contain sections for prerequisites, creating suites, adding tests to suites, executing suites, managing suites, and error handling/troubleshooting
3. THE SKILL_File for `qa-studio-suites` SHALL include concrete CLI command examples with realistic placeholder values for each operation
4. THE SKILL_File for `qa-studio-suites` SHALL instruct the agent to check authentication via `qa-studio status` before attempting any operation

### Requirement 4: Skills Directory Structure

**User Story:** As a developer, I want the skills to be bundled inside the CLI package in a well-organized directory structure, so that they ship with the tool and can be symlinked into the Kiro IDE.

#### Acceptance Criteria

1. THE Skills_Directory SHALL be located at `qa-studio-cli/skills/` within the CLI package
2. THE Skills_Directory SHALL contain a `qa-studio-tests/` subdirectory with `SKILL.md` and a `reference/` subdirectory containing `step-types.md`, `validation-operators.md`, and `manual-creation.md`
3. THE Skills_Directory SHALL contain a `qa-studio-suites/` subdirectory with `SKILL.md`
4. THE CLI package `setup.py` SHALL include the `skills/` directory and all its contents as package data so they are distributed with the package

### Requirement 5: Skills Installation Command

**User Story:** As a developer, I want a `qa-studio setup` command that installs skills into my Kiro IDE, so that the Kiro agent can discover and use QA Studio capabilities.

#### Acceptance Criteria

1. WHEN a user runs `qa-studio setup`, THE Skills_Manager SHALL check that the `~/.kiro/` directory exists
2. IF the `~/.kiro/` directory does not exist, THEN THE Skills_Manager SHALL display a warning that Kiro IDE is not detected and instruct the user to install Kiro IDE first
3. WHEN the `~/.kiro/` directory exists, THE Skills_Manager SHALL create `~/.kiro/skills/` if the directory does not exist
4. WHEN installing skills, THE Skills_Manager SHALL create a symlink from `~/.kiro/skills/<skill-name>` to the corresponding directory in the Skills_Directory for each skill that contains a `SKILL.md` file
5. WHEN a symlink for a skill already exists and points to the correct target, THE Skills_Manager SHALL display that the skill is already installed and skip re-creation
6. WHEN a path exists at `~/.kiro/skills/<skill-name>` that is not a symlink, THE Skills_Manager SHALL display a warning that the path exists but is not a symlink and skip that skill
7. WHEN installation completes with at least one new skill installed, THE Skills_Manager SHALL display the count of installed skills and next-step guidance to run `qa-studio login`
8. WHEN all skills are already installed, THE Skills_Manager SHALL display that all skills are already installed
9. IF symlink creation fails due to an OS error, THEN THE Skills_Manager SHALL display the skill name and the error message and continue with remaining skills

### Requirement 6: Skills Uninstall Command

**User Story:** As a developer, I want a `qa-studio uninstall` command that removes skill symlinks, so that I can cleanly remove QA Studio integration from my Kiro IDE.

#### Acceptance Criteria

1. WHEN a user runs `qa-studio uninstall`, THE Skills_Manager SHALL iterate over all skill directories in the Skills_Directory
2. WHEN a symlink exists at `~/.kiro/skills/<skill-name>`, THE Skills_Manager SHALL remove the symlink and display a confirmation message
3. WHEN no symlinks exist for any skill, THE Skills_Manager SHALL display that there are no skills to remove
4. WHEN at least one symlink is removed, THE Skills_Manager SHALL display the count of removed skills
5. THE `qa-studio uninstall` command SHALL only remove symlinks and SHALL NOT delete non-symlink files or directories at `~/.kiro/skills/<skill-name>`

### Requirement 7: Enhanced Status Command

**User Story:** As a developer, I want `qa-studio status` to show skills installation status alongside authentication status, so that I can see the full state of my QA Studio CLI setup at a glance.

#### Acceptance Criteria

1. WHEN a user runs `qa-studio status`, THE CLI SHALL display the authentication status as before (authenticated or not authenticated)
2. WHEN a user runs `qa-studio status`, THE CLI SHALL display a "Skills:" section listing each skill from the Skills_Directory
3. WHEN a skill symlink exists and is valid at `~/.kiro/skills/<skill-name>`, THE CLI SHALL display the skill name with a checkmark indicator
4. WHEN a skill symlink does not exist at `~/.kiro/skills/<skill-name>`, THE CLI SHALL display the skill name with a cross indicator and "(not installed)" label
5. WHEN any skills are not installed, THE CLI SHALL display guidance to run `qa-studio setup`

### Requirement 8: Skills Manager Module

**User Story:** As a developer, I want the skills management logic encapsulated in a dedicated module, so that the setup, uninstall, and status commands share consistent behavior and the code remains DRY.

#### Acceptance Criteria

1. THE Skills_Manager SHALL be implemented as a module at `qa-studio-cli/qa_studio_cli/skills/manager.py`
2. THE Skills_Manager SHALL provide a function to resolve the path to the bundled Skills_Directory relative to the package installation
3. THE Skills_Manager SHALL provide a function to list all available skills by scanning the Skills_Directory for subdirectories containing a `SKILL.md` file
4. THE Skills_Manager SHALL provide a function to check the installation status of each skill (installed, not installed, conflict)
5. THE Skills_Manager SHALL provide a function to install all skills as symlinks
6. THE Skills_Manager SHALL provide a function to uninstall all skill symlinks
7. THE Skills_Manager SHALL use `pathlib.Path` for all filesystem operations

### Requirement 9: Skill Content Quality

**User Story:** As a developer, I want the skills to follow Kiro Agent Skills best practices, so that the Kiro agent can effectively use them to assist with QA Studio workflows.

#### Acceptance Criteria

1. THE SKILL_File content SHALL use progressive disclosure by keeping the main file concise and linking to reference files for detailed content
2. THE SKILL_File descriptions SHALL be written in third person (e.g., "Create and manage QA Studio UI tests" not "I create and manage")
3. THE SKILL_File content SHALL prioritize concrete examples over explanatory prose
4. THE SKILL_File content SHALL reference only CLI commands that exist or are planned for WP4 (tests list, tests get, tests create, tests delete, suites list, suites get, suites create, suites add-tests, suites remove-test)
5. THE Reference_File content SHALL use consistent formatting with description, required fields, examples, and when-to-use sections for each documented item
6. THE SKILL_File content SHALL use only forward slashes in file paths and relative links
7. THE SKILL_File content SHALL only include QA Studio-specific knowledge and SHALL NOT explain general concepts the agent already knows (e.g., what URLs are, how CLI arguments work, what JSON is) to maximize token efficiency
8. THE SKILL_File descriptions SHALL include specific trigger keywords that help the agent match user intent to the correct skill

### Requirement 10: Testing

**User Story:** As a developer, I want comprehensive test coverage for the skills management functionality, so that installation, uninstallation, and status reporting work reliably across environments.

#### Acceptance Criteria

1. THE test suite SHALL achieve at least 70% unit test coverage for the Skills_Manager module
2. THE test suite SHALL include tests for skill installation covering: successful symlink creation, already-installed skip, non-symlink conflict warning, missing Kiro directory warning, and OS error handling
3. THE test suite SHALL include tests for skill uninstallation covering: successful symlink removal, no-symlinks-to-remove scenario, and non-symlink skip
4. THE test suite SHALL include tests for skill status checking covering: installed skills, not-installed skills, and mixed states
5. THE test suite SHALL include tests for the `setup`, `uninstall`, and enhanced `status` CLI commands using Click's `CliRunner`
6. THE test suite SHALL validate that all SKILL_File files contain valid YAML frontmatter with `name` and `description` fields
7. THE test suite SHALL validate that all SKILL_File files are under 500 lines
