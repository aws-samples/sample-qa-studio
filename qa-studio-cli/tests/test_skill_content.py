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
        "assertion", "download", "transform", "network_assertion",
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
