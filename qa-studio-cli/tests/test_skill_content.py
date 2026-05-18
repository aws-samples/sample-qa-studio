"""Content validation tests for the unified QA Studio agent skill.

Validates that SKILL.md and reference files meet quality standards:
- Frontmatter contains required trigger keywords
- Required sections exist
- Error handling covers expected scenarios (in reference/troubleshooting.md)
- Reference files have TOCs
- SKILL.md stays under 500 lines
"""

import re
from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
SKILL_FILE = SKILLS_DIR / "qa-studio" / "SKILL.md"
REFERENCE_DIR = SKILLS_DIR / "qa-studio" / "reference"


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
    """Validate that SKILL.md frontmatter description contains required trigger keywords."""

    REQUIRED_KEYWORDS = [
        "browser-based UI tests",
        "test web applications",
        "automated browser tests",
        "UI tests",
        "CI/CD",
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
            "## Quick Start",
            "## Decision Tree",
            "## Common Workflows",
            "## Examples",
            "## Reference Documentation",
            "## Key Concepts",
            "## Authentication Models",
            "## Error Handling",
        ],
        ids=[
            "quick_start",
            "decision_tree",
            "common_workflows",
            "examples",
            "reference_docs",
            "key_concepts",
            "auth_models",
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
            "configuration",
            "suite",
        ],
        ids=[
            "auth_failure",
            "not_found",
            "execution_failure",
            "timeout",
            "configuration",
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
    ]

    def test_step_types_has_all_7_step_types(self):
        step_types_file = REFERENCE_DIR / "step-types.md"
        content = step_types_file.read_text()
        for step_type in self.STEP_TYPES:
            assert step_type in content, (
                f"step-types.md missing step type '{step_type}'"
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
        "step-types.md",
        "validation-operators.md",
        "creating-tests.md",
        "local-execution.md",
        "test-suites.md",
        "managing-tests.md",
        "ci-cd-integration.md",
        "troubleshooting.md",
        "best-practices.md",
        "web-interface.md",
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
    """Validate all SKILL.md files stay under 500 lines."""

    MAX_LINES = 500

    def _get_all_skill_files(self):
        """Return all SKILL.md files in the skills directory."""
        return list(SKILLS_DIR.glob("*/SKILL.md"))

    def test_all_skill_files_under_500_lines(self):
        skill_files = self._get_all_skill_files()
        assert skill_files, "No SKILL.md files found"
        for skill_file in skill_files:
            line_count = len(skill_file.read_text().splitlines())
            assert line_count < self.MAX_LINES, (
                f"{skill_file.parent.name}/SKILL.md has {line_count} lines, "
                f"expected <{self.MAX_LINES}"
            )
