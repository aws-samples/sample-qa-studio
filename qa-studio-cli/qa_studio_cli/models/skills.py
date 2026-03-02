"""Pydantic models for skill discovery and lifecycle management."""

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class SkillInfo(BaseModel):
    """Metadata about a bundled skill discovered in the skills directory."""

    name: str = Field(..., description="Skill directory name (e.g. 'qa-studio-tests')")
    path: Path = Field(
        ..., description="Absolute path to the skill directory in the package"
    )

    model_config = {"arbitrary_types_allowed": True}


class SkillState(str, Enum):
    """Possible installation states for a skill."""

    INSTALLED = "installed"
    NOT_INSTALLED = "not_installed"
    CONFLICT = "conflict"
    INSTALL_FAILED = "install_failed"
    REMOVED = "removed"
    SKIPPED = "skipped"


class SkillStatus(BaseModel):
    """Installation status of a single skill."""

    name: str = Field(..., description="Skill name")
    state: SkillState = Field(..., description="Current installation state")
    message: str = Field(default="", description="Human-readable status message")


class SkillFrontmatter(BaseModel):
    """YAML frontmatter parsed from a SKILL.md file."""

    name: str = Field(..., min_length=1, description="Skill name matching directory name")
    description: str = Field(
        ..., min_length=1, description="Third-person skill description"
    )
