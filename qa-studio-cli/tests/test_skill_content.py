"""Content validation tests for the unified QA Studio agent skill.

Validates that SKILL.md and reference files meet quality standards:
- Frontmatter contains required trigger keywords
- Required sections exist
- Error handling covers expected scenarios (in reference/troubleshooting.md)
- Reference files have TOCs
- SKILL.md stays under 500 lines
"""

import json
import re
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent.parent / "skill"
SKILL_FILE = SKILL_DIR / "SKILL.md"
REFERENCE_DIR = SKILL_DIR / "reference"


def _parse_frontmatter(path: Path) -> str:
    """Extract the YAML frontmatter description from a SKILL.md file."""
    text = path.read_text()
    parts = text.split("---", 2)
    assert len(parts) >= 3, f"No valid frontmatter in {path}"
    return parts[1]


def _read_content(path: Path) -> str:
    """Read the full content of a file."""
    return path.read_text()


# ---------------------------------------------------------------------------
# Frontmatter keyword tests
# ---------------------------------------------------------------------------


class TestFrontmatterKeywords:
    """Validate that SKILL.md frontmatter description contains required trigger keywords.

    Keywords are intentionally narrow: the skill covers test authoring and
    execution only. CI/CD and similar broader topics deliberately do not
    appear in the description so the skill is not activated for queries it
    cannot answer.
    """

    REQUIRED_KEYWORDS = [
        "browser-based UI tests",
        "build a test case",
        "execute",
        "Nova Act",
    ]

    def test_has_required_trigger_keywords(self):
        frontmatter = _parse_frontmatter(SKILL_FILE)
        for keyword in self.REQUIRED_KEYWORDS:
            assert keyword.lower() in frontmatter.lower(), (
                f"qa-studio description missing keyword: '{keyword}'"
            )

    def test_has_name_field(self):
        frontmatter = _parse_frontmatter(SKILL_FILE)
        assert "name: qa-studio" in frontmatter


# ---------------------------------------------------------------------------
# Section existence tests
# ---------------------------------------------------------------------------


class TestSectionExistence:
    """Validate that SKILL.md contains required sections."""

    @pytest.mark.parametrize(
        "section",
        [
            "## Decision Tree",
            "## Common Workflows",
            "## Examples",
            "## Reference Documentation",
            "## Key Concepts",
            "## Error Handling",
        ],
        ids=[
            "decision_tree",
            "common_workflows",
            "examples",
            "reference_docs",
            "key_concepts",
            "error_handling",
        ],
    )
    def test_has_required_section(self, section):
        content = _read_content(SKILL_FILE)
        assert section in content, f"SKILL.md missing '{section}' section"

    def test_has_at_least_3_examples(self):
        content = _read_content(SKILL_FILE)
        example_count = len(re.findall(r"###\s+Example", content))
        assert example_count >= 3, (
            f"SKILL.md has {example_count} examples, expected ≥3"
        )

    def test_has_at_least_3_workflows(self):
        content = _read_content(SKILL_FILE)
        workflow_count = len(re.findall(r"###\s+Workflow", content))
        assert workflow_count >= 3, (
            f"SKILL.md has {workflow_count} workflows, expected ≥3"
        )


# ---------------------------------------------------------------------------
# Error handling content tests (now in reference/troubleshooting.md)
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Validate troubleshooting reference covers required error scenarios."""

    TROUBLESHOOTING = REFERENCE_DIR / "troubleshooting.md"

    @pytest.mark.parametrize(
        "topic",
        [
            "authentication",
            "not found",
            "execution",
            "timeout",
            "suite",
        ],
        ids=[
            "auth_failure",
            "not_found",
            "execution_failure",
            "timeout",
            "suite_errors",
        ],
    )
    def test_troubleshooting_covers_topic(self, topic):
        content = _read_content(self.TROUBLESHOOTING)
        assert topic.lower() in content.lower(), (
            f"troubleshooting.md missing coverage for: '{topic}'"
        )

    def test_troubleshooting_has_debugging_workflow(self):
        content = _read_content(self.TROUBLESHOOTING)
        assert "## Debugging Workflow" in content


# ---------------------------------------------------------------------------
# Reference file TOC tests
# ---------------------------------------------------------------------------


class TestReferenceTOC:
    """Validate reference files have proper tables of contents."""

    ANCHOR_LINK_PATTERN = re.compile(r"\[.*?\]\(.*?\)")

    def _get_reference_files_over_100_lines(self):
        """Return all reference .md files exceeding 100 lines."""
        files = []
        for md_file in REFERENCE_DIR.glob("*.md"):
            line_count = len(md_file.read_text().splitlines())
            if line_count > 100:
                files.append(md_file)
        return files

    def test_all_large_reference_files_have_structure_in_first_20_lines(self):
        """Large reference files should have a heading or link structure early on."""
        large_files = self._get_reference_files_over_100_lines()
        assert large_files, "Expected at least one reference file over 100 lines"
        heading_pattern = re.compile(r"^#{1,3}\s+", re.MULTILINE)
        for md_file in large_files:
            first_20_lines = "\n".join(md_file.read_text().splitlines()[:20])
            has_links = self.ANCHOR_LINK_PATTERN.search(first_20_lines)
            has_headings = len(heading_pattern.findall(first_20_lines)) >= 2
            assert has_links or has_headings, (
                f"{md_file.name} (>100 lines) has no structure in first 20 lines"
            )

    STEP_TYPES = [
        "navigation",
        "url",
        "secret",
        "validation",
        "retrieve_value",
        "assertion",
        "download",
        "browser",
        "transform",
        "network_assertion",
        "repeat",
    ]

    def test_step_types_directory_has_one_file_per_step_type(self):
        """Each step type has its own dedicated reference file."""
        step_types_dir = REFERENCE_DIR / "step-types"
        assert step_types_dir.is_dir(), "step-types/ directory missing"
        for step_type in self.STEP_TYPES:
            filepath = step_types_dir / f"{step_type}.md"
            assert filepath.is_file(), (
                f"step-types/{step_type}.md missing — every step type "
                "needs its own reference file"
            )

    def test_step_types_directory_has_readme_index(self):
        """A README.md at the directory root provides the decision tree."""
        readme = REFERENCE_DIR / "step-types" / "README.md"
        assert readme.is_file(), "step-types/README.md missing"

    @pytest.mark.parametrize("step_type", [
        "navigation", "browser", "secret", "validation", "retrieve_value",
        "assertion", "download", "transform", "network_assertion", "repeat",
    ])
    def test_step_type_file_has_required_sections(self, step_type):
        """Each (non-deprecated) step type file follows the standard template."""
        filepath = REFERENCE_DIR / "step-types" / f"{step_type}.md"
        content = filepath.read_text()
        for section in ["## When to use", "## When NOT to use", "## Inputs", "## Examples", "## Common pitfalls"]:
            assert section in content, (
                f"step-types/{step_type}.md missing required section: '{section}'"
            )

    def test_validation_operators_grouped_by_category(self):
        val_ops_file = REFERENCE_DIR / "validation-operators.md"
        content = val_ops_file.read_text()
        for category in ["String", "Number", "Boolean", "Date"]:
            assert f"## {category}" in content, (
                f"validation-operators.md missing category group: '{category}'"
            )


# ---------------------------------------------------------------------------
# Reference file completeness
# ---------------------------------------------------------------------------


class TestReferenceCompleteness:
    """Validate all expected reference files exist."""

    EXPECTED_REFERENCE_FILES = [
        "validation-operators.md",
        "building-tests.md",
        "executing-tests.md",
        "troubleshooting.md",
    ]

    def test_all_reference_files_exist(self):
        for filename in self.EXPECTED_REFERENCE_FILES:
            filepath = REFERENCE_DIR / filename
            assert filepath.is_file(), f"Missing reference file: {filename}"

    def test_reference_files_are_non_empty(self):
        for filename in self.EXPECTED_REFERENCE_FILES:
            filepath = REFERENCE_DIR / filename
            content = filepath.read_text().strip()
            assert len(content) > 50, (
                f"Reference file {filename} appears empty or too short"
            )


# ---------------------------------------------------------------------------
# SKILL.md line limit tests
# ---------------------------------------------------------------------------


class TestLineLimit:
    """Enforce a tight cap on SKILL.md to keep detail in the reference files."""

    MAX_LINES = 300

    def test_skill_file_under_max_lines(self):
        line_count = len(SKILL_FILE.read_text().splitlines())
        assert line_count < self.MAX_LINES, (
            f"SKILL.md is {line_count} lines (max {self.MAX_LINES}). "
            "Move detail to reference files."
        )


# ---------------------------------------------------------------------------
# Templates (reuse steps across tests)
# ---------------------------------------------------------------------------


class TestTemplatesInSkill:
    """The skill must steer agents to reuse templates before hand-authoring repeated steps."""

    TEMPLATES_REF = REFERENCE_DIR / "templates.md"

    def test_templates_reference_exists_and_is_linked(self):
        assert self.TEMPLATES_REF.is_file(), "reference/templates.md missing"
        assert "reference/templates.md" in _read_content(SKILL_FILE)

    def test_description_mentions_templates(self):
        assert "template" in _parse_frontmatter(SKILL_FILE).lower()

    def test_decision_tree_has_reuse_branch(self):
        content = _read_content(SKILL_FILE)
        assert "Reuse steps across tests (templates)" in content
        assert "qa-studio templates list" in content
        assert "tests insert-template" in content

    def test_key_concepts_has_template(self):
        content = _read_content(SKILL_FILE)
        assert re.search(r"^### Template\s*$", content, re.MULTILINE), "Key Concepts lacks a 'Template' entry"

    def test_reimport_wording_is_accurate(self):
        """``tests import`` always creates a new use case — it never overwrites by name."""
        assert "overwriting the previous version" not in _read_content(SKILL_FILE)

    def test_templates_reference_covers_required_topics(self):
        content = _read_content(self.TEMPLATES_REF)
        for fragment in (
            "templateVersion", '"step_type": "template"', "template_id", "qa-studio templates create",
            "qa-studio templates get", "qa-studio tests insert-template", "--position", "--secret",
            "environment", "secret_key", "nest", "one action or one check",
        ):
            assert fragment.lower() in content.lower(), f"templates.md lacks '{fragment}'"

    def test_building_tests_documents_placeholder_step(self):
        content = _read_content(REFERENCE_DIR / "building-tests.md")
        assert '"step_type": "template"' in content
        assert "reference/templates.md" in content or "./templates.md" in content

    def test_evals_cover_reuse_and_create(self):
        evals = json.loads((SKILL_DIR / "evals" / "evals.json").read_text())["evals"]
        prompts = " ".join(e["prompt"].lower() + " " + e["expected_output"].lower() for e in evals)
        assert "templates list" in prompts, "no eval exercises reusing an existing template"
        assert "templates create" in prompts, "no eval exercises creating a template then referencing it"

    def test_every_documented_template_command_exists(self):
        """Each ``qa-studio templates <cmd>`` / ``tests insert-template --flag`` in the skill is real."""
        from qa_studio_cli.cli import cli

        content = _read_content(self.TEMPLATES_REF) + _read_content(SKILL_FILE)
        template_cmds = set(re.findall(r"qa-studio templates ([a-z-]+)", content))
        assert template_cmds <= set(cli.commands["templates"].commands), template_cmds - set(cli.commands["templates"].commands)

        insert_cmd = cli.commands["tests"].commands["insert-template"]
        real_flags = {opt for p in insert_cmd.params for opt in getattr(p, "opts", [])}
        for block in re.findall(r"qa-studio tests insert-template([^\n`]*)", content):
            for flag in re.findall(r"(--[a-z-]+)", block):
                assert flag in real_flags, f"insert-template has no flag {flag}"



# ---------------------------------------------------------------------------
# Quiet run output (cli-quiet-run-output)
# ---------------------------------------------------------------------------


class TestExecutionOutputGuidance:
    """The skill must describe the real ``qa-studio run`` output contract."""

    EXECUTING = REFERENCE_DIR / "executing-tests.md"
    TROUBLESHOOTING = REFERENCE_DIR / "troubleshooting.md"

    def test_quotes_real_progress_line_formats(self):
        from qa_studio_cli.runner import progress

        content = _read_content(self.EXECUTING)
        # The constants rendered as the docs show them (time placeholder spelled out).
        assert progress.TEST_STARTED_FORMAT.replace("{time}", "HH:MM:SS") in content
        assert "Step {n}: {instruction}" in content
        assert "[{test name}]" in content or "[<test name>]" in content

    def test_stale_output_examples_are_gone(self):
        content = _read_content(self.EXECUTING)
        assert "Step 1/4" not in content
        assert "duration_ms" not in content
        assert '"execution_id"' not in content and '"usecase_id"' not in content

    def test_json_example_uses_real_camel_case_schema(self):
        content = _read_content(self.EXECUTING)
        for field in ("usecaseId", "usecaseName", "executionId", "stepId", "stepType", '"artifacts"'):
            assert field in content, f"executing-tests.md lacks JSON field {field}"

    def test_states_stream_split_and_verbose_scope(self):
        content = _read_content(self.EXECUTING).lower()
        assert "stderr" in content and "stdout" in content
        assert "2>/dev/null" in content
        for phrase in ("think/act", "api calls", "--verbose"):
            assert phrase in content, f"executing-tests.md lacks '{phrase}'"

    def test_troubleshooting_notes_console_needs_verbose(self):
        content = _read_content(self.TROUBLESHOOTING)
        assert "--verbose" in content
        assert "console only shows" in content.lower()

    def test_eval_covers_missing_reasoning_question(self):
        evals = json.loads((SKILL_DIR / "evals" / "evals.json").read_text())["evals"]
        matching = [e for e in evals if "--verbose" in e["expected_output"] and "Step" in e["prompt"]]
        assert matching, "no eval exercises 'where is the Nova Act reasoning / API calls?'"
        expected = matching[0]["expected_output"]
        assert "--debug" in expected or "--log-level" in expected, "eval must forbid non-existent flags"
        assert "artifacts.logs" in expected or "logs" in expected
