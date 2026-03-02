"""Skill discovery, installation, uninstallation, and status checking.

Copies bundled skills from the package's skills/ directory into
~/.kiro/skills/ where the Kiro IDE discovers them.
"""

import shutil
from pathlib import Path

from qa_studio_cli.models.skills import SkillInfo, SkillState, SkillStatus

KIRO_DIR = Path.home() / ".kiro"
KIRO_SKILLS_DIR = KIRO_DIR / "skills"

# Skills that were replaced by the unified 'qa-studio' skill.
# Cleaned up during install/uninstall so users don't keep stale copies.
LEGACY_SKILL_NAMES = ["qa-studio-tests", "qa-studio-suites", "qa-studio-ci-runner"]


def get_skills_directory() -> Path:
    """Resolve the path to the bundled skills/ directory relative to this package.

    Returns:
        Absolute path to qa-studio-cli/skills/
    """
    return Path(__file__).resolve().parent.parent.parent / "skills"


def list_available_skills() -> list[SkillInfo]:
    """Scan the bundled skills directory for subdirectories containing SKILL.md.

    Returns:
        Sorted list of SkillInfo with name and path for each discovered skill.
    """
    skills_dir = get_skills_directory()
    if not skills_dir.is_dir():
        return []

    skills: list[SkillInfo] = []
    for entry in sorted(skills_dir.iterdir()):
        if entry.is_dir() and (entry / "SKILL.md").is_file():
            skills.append(SkillInfo(name=entry.name, path=entry))
    return skills


def is_kiro_installed() -> bool:
    """Check if ~/.kiro/ directory exists."""
    return KIRO_DIR.is_dir()


def check_skill_status(skill: SkillInfo) -> SkillStatus:
    """Check installation status of a single skill.

    Returns:
        SkillStatus with state INSTALLED (directory with SKILL.md exists),
        CONFLICT (path exists but has no SKILL.md), or NOT_INSTALLED.
    """
    target = KIRO_SKILLS_DIR / skill.name

    if target.is_dir() and (target / "SKILL.md").is_file():
        return SkillStatus(
            name=skill.name,
            state=SkillState.INSTALLED,
            message="Installed",
        )

    if target.exists() or target.is_symlink():
        return SkillStatus(
            name=skill.name,
            state=SkillState.CONFLICT,
            message=f"{skill.name} exists but is not a valid skill — skipped",
        )

    return SkillStatus(
        name=skill.name,
        state=SkillState.NOT_INSTALLED,
        message="Not installed",
    )


def check_all_skills_status() -> list[SkillStatus]:
    """Check installation status of all available skills.

    Returns:
        List of SkillStatus for each available skill.
    """
    return [check_skill_status(skill) for skill in list_available_skills()]


def _remove_legacy_skills() -> list[SkillStatus]:
    """Remove legacy skill directories that were replaced by the unified skill.

    Returns:
        List of SkillStatus for each removed legacy skill.
    """
    results: list[SkillStatus] = []
    for name in LEGACY_SKILL_NAMES:
        target = KIRO_SKILLS_DIR / name
        if target.is_symlink():
            target.unlink()
            results.append(SkillStatus(
                name=name,
                state=SkillState.REMOVED,
                message=f"Removed legacy skill {name} (was symlink)",
            ))
        elif target.is_dir():
            shutil.rmtree(target)
            results.append(SkillStatus(
                name=name,
                state=SkillState.REMOVED,
                message=f"Removed legacy skill {name}",
            ))
    return results


def install_skills() -> list[SkillStatus]:
    """Install all available skills by copying them into ~/.kiro/skills/.

    Creates ~/.kiro/skills/ if it doesn't exist. Skips already-installed
    skills and conflict paths. OS errors are caught per-skill and reported
    in the returned status list.

    Returns:
        List of SkillStatus with outcome for each skill.
        Empty list if ~/.kiro/ does not exist.
    """
    if not is_kiro_installed():
        return []

    KIRO_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    # Clean up legacy skills replaced by the unified 'qa-studio' skill
    legacy_results = _remove_legacy_skills()

    results: list[SkillStatus] = []
    for skill in list_available_skills():
        target = KIRO_SKILLS_DIR / skill.name

        if target.is_dir() and (target / "SKILL.md").is_file():
            results.append(SkillStatus(
                name=skill.name,
                state=SkillState.INSTALLED,
                message="Already installed",
            ))
            continue

        if target.exists() or target.is_symlink():
            results.append(SkillStatus(
                name=skill.name,
                state=SkillState.CONFLICT,
                message=f"{skill.name} exists but is not a valid skill — skipped",
            ))
            continue

        try:
            shutil.copytree(skill.path, target)
            results.append(SkillStatus(
                name=skill.name,
                state=SkillState.INSTALLED,
                message=f"Installed {skill.name}",
            ))
        except OSError as exc:
            results.append(SkillStatus(
                name=skill.name,
                state=SkillState.INSTALL_FAILED,
                message=f"Failed to install {skill.name}: {exc}",
            ))

    return legacy_results + results


def uninstall_skills() -> list[SkillStatus]:
    """Remove all installed skill directories from ~/.kiro/skills/.

    Only removes directories that contain a SKILL.md (i.e. were installed
    by this tool). Stale symlinks from previous versions are also cleaned up.
    Legacy skills replaced by the unified skill are also removed.

    Returns:
        List of SkillStatus with outcome for each skill.
    """
    # Clean up legacy skills replaced by the unified 'qa-studio' skill
    legacy_results = _remove_legacy_skills()

    results: list[SkillStatus] = []
    for skill in list_available_skills():
        target = KIRO_SKILLS_DIR / skill.name

        # Clean up stale symlinks from previous versions
        if target.is_symlink():
            target.unlink()
            results.append(SkillStatus(
                name=skill.name,
                state=SkillState.REMOVED,
                message=f"Removed {skill.name} (was symlink)",
            ))
        elif target.is_dir() and (target / "SKILL.md").is_file():
            shutil.rmtree(target)
            results.append(SkillStatus(
                name=skill.name,
                state=SkillState.REMOVED,
                message=f"Removed {skill.name}",
            ))
        elif target.exists():
            results.append(SkillStatus(
                name=skill.name,
                state=SkillState.SKIPPED,
                message=f"{skill.name} is not a valid skill — skipped",
            ))
        else:
            results.append(SkillStatus(
                name=skill.name,
                state=SkillState.NOT_INSTALLED,
                message="Not installed",
            ))

    return legacy_results + results
