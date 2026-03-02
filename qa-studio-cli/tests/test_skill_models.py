"""Unit tests for Pydantic skill models."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from qa_studio_cli.models.skills import (
    SkillFrontmatter,
    SkillInfo,
    SkillState,
    SkillStatus,
)


class TestSkillInfo:
    def test_accepts_path_objects(self, tmp_path):
        info = SkillInfo(name="my-skill", path=tmp_path / "skills" / "my-skill")
        assert info.name == "my-skill"
        assert isinstance(info.path, Path)

    def test_accepts_string_path(self):
        info = SkillInfo(name="my-skill", path="/some/path")
        assert isinstance(info.path, Path)

    def test_requires_name(self):
        with pytest.raises(ValidationError):
            SkillInfo(path=Path("/tmp"))


class TestSkillState:
    def test_enum_values(self):
        assert SkillState.INSTALLED == "installed"
        assert SkillState.NOT_INSTALLED == "not_installed"
        assert SkillState.CONFLICT == "conflict"
        assert SkillState.INSTALL_FAILED == "install_failed"
        assert SkillState.REMOVED == "removed"
        assert SkillState.SKIPPED == "skipped"

    def test_is_string_subclass(self):
        assert isinstance(SkillState.INSTALLED, str)


class TestSkillStatus:
    def test_defaults_message_to_empty_string(self):
        status = SkillStatus(name="test", state=SkillState.INSTALLED)
        assert status.message == ""

    def test_accepts_custom_message(self):
        status = SkillStatus(
            name="test", state=SkillState.CONFLICT, message="conflict detected"
        )
        assert status.message == "conflict detected"

    def test_requires_name_and_state(self):
        with pytest.raises(ValidationError):
            SkillStatus(state=SkillState.INSTALLED)
        with pytest.raises(ValidationError):
            SkillStatus(name="test")


class TestSkillFrontmatter:
    def test_valid_frontmatter(self):
        fm = SkillFrontmatter(name="qa-studio-tests", description="A test skill")
        assert fm.name == "qa-studio-tests"
        assert fm.description == "A test skill"

    def test_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            SkillFrontmatter(name="", description="Valid description")

    def test_rejects_empty_description(self):
        with pytest.raises(ValidationError):
            SkillFrontmatter(name="valid-name", description="")

    def test_rejects_missing_fields(self):
        with pytest.raises(ValidationError):
            SkillFrontmatter(name="only-name")
        with pytest.raises(ValidationError):
            SkillFrontmatter(description="only-desc")
