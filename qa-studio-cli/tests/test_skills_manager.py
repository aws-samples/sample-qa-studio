"""Unit tests for the skills manager module."""

import shutil
from pathlib import Path

import pytest

from qa_studio_cli.models.skills import SkillInfo, SkillState
from qa_studio_cli.skills.manager import (
    LEGACY_SKILL_NAMES,
    check_all_skills_status,
    check_skill_status,
    get_skills_directory,
    install_skills,
    is_kiro_installed,
    list_available_skills,
    uninstall_skills,
)


class TestGetSkillsDirectory:
    def test_returns_existing_path(self):
        result = get_skills_directory()
        assert result.is_dir()
        assert result.name == "skills"

    def test_returns_absolute_path(self):
        result = get_skills_directory()
        assert result.is_absolute()


class TestListAvailableSkills:
    def test_returns_correct_skills_from_bundled_directory(self):
        skills = list_available_skills()
        names = [s.name for s in skills]
        assert names == ["qa-studio"]

    def test_ignores_directories_without_skill_md(self, tmp_path, monkeypatch):
        skills_dir = tmp_path / "skills"
        valid = skills_dir / "valid-skill"
        valid.mkdir(parents=True)
        (valid / "SKILL.md").write_text("---\nname: valid-skill\n---\n")
        invalid = skills_dir / "no-skill-md"
        invalid.mkdir()
        (invalid / "README.md").write_text("not a skill")

        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.get_skills_directory",
            lambda: skills_dir,
        )
        skills = list_available_skills()
        assert len(skills) == 1
        assert skills[0].name == "valid-skill"

    def test_returns_empty_when_skills_dir_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.get_skills_directory",
            lambda: tmp_path / "nonexistent",
        )
        assert list_available_skills() == []

    def test_returns_sorted_by_name(self):
        skills = list_available_skills()
        names = [s.name for s in skills]
        assert names == sorted(names)


class TestIsKiroInstalled:
    def test_returns_true_when_kiro_dir_exists(self, tmp_kiro_dir, monkeypatch):
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_DIR", tmp_kiro_dir
        )
        assert is_kiro_installed() is True

    def test_returns_false_when_kiro_dir_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_DIR", tmp_path / "no-kiro"
        )
        assert is_kiro_installed() is False


class TestCheckSkillStatus:
    def test_returns_installed_for_copied_skill(
        self, tmp_path, tmp_skills_source, monkeypatch
    ):
        kiro_skills = tmp_path / ".kiro" / "skills"
        kiro_skills.mkdir(parents=True)
        installed = kiro_skills / "qa-studio"
        installed.mkdir()
        (installed / "SKILL.md").write_text("---\nname: qa-studio\n---\n")

        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        skill = SkillInfo(name="qa-studio", path=tmp_skills_source / "qa-studio")
        status = check_skill_status(skill)
        assert status.state == SkillState.INSTALLED

    def test_returns_not_installed_for_missing_path(
        self, tmp_path, monkeypatch
    ):
        kiro_skills = tmp_path / ".kiro" / "skills"
        kiro_skills.mkdir(parents=True)

        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        skill = SkillInfo(name="missing-skill", path=tmp_path / "src")
        status = check_skill_status(skill)
        assert status.state == SkillState.NOT_INSTALLED

    def test_returns_conflict_for_directory_without_skill_md(
        self, tmp_path, monkeypatch
    ):
        kiro_skills = tmp_path / ".kiro" / "skills"
        kiro_skills.mkdir(parents=True)
        (kiro_skills / "conflict-skill").mkdir()

        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        skill = SkillInfo(name="conflict-skill", path=tmp_path / "src")
        status = check_skill_status(skill)
        assert status.state == SkillState.CONFLICT

    def test_returns_conflict_for_stale_symlink(
        self, tmp_path, tmp_skills_source, monkeypatch
    ):
        kiro_skills = tmp_path / ".kiro" / "skills"
        kiro_skills.mkdir(parents=True)
        (kiro_skills / "qa-studio").symlink_to(
            tmp_skills_source / "qa-studio"
        )

        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        skill = SkillInfo(name="qa-studio", path=tmp_skills_source / "qa-studio")
        status = check_skill_status(skill)
        # Symlinks resolve to a dir with SKILL.md, so they appear installed
        assert status.state == SkillState.INSTALLED


class TestCheckAllSkillsStatus:
    def test_returns_status_for_each_skill(
        self, tmp_path, tmp_skills_source, monkeypatch
    ):
        kiro_skills = tmp_path / ".kiro" / "skills"
        kiro_skills.mkdir(parents=True)

        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.get_skills_directory",
            lambda: tmp_skills_source,
        )
        statuses = check_all_skills_status()
        assert len(statuses) == 1
        assert statuses[0].name == "qa-studio"


class TestInstallSkills:
    def test_copies_skill_directory(
        self, tmp_path, tmp_skills_source, monkeypatch
    ):
        kiro_dir = tmp_path / ".kiro"
        kiro_dir.mkdir()
        kiro_skills = kiro_dir / "skills"

        monkeypatch.setattr("qa_studio_cli.skills.manager.KIRO_DIR", kiro_dir)
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.get_skills_directory",
            lambda: tmp_skills_source,
        )

        results = install_skills()
        installed = [r for r in results if r.state == SkillState.INSTALLED]
        assert len(installed) == 1
        assert (kiro_skills / "qa-studio").is_dir()
        assert not (kiro_skills / "qa-studio").is_symlink()
        assert (kiro_skills / "qa-studio" / "SKILL.md").is_file()

    def test_creates_skills_directory(
        self, tmp_path, tmp_skills_source, monkeypatch
    ):
        kiro_dir = tmp_path / ".kiro"
        kiro_dir.mkdir()
        kiro_skills = kiro_dir / "skills"

        monkeypatch.setattr("qa_studio_cli.skills.manager.KIRO_DIR", kiro_dir)
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.get_skills_directory",
            lambda: tmp_skills_source,
        )

        assert not kiro_skills.exists()
        install_skills()
        assert kiro_skills.is_dir()

    def test_skips_already_installed_skill(
        self, tmp_path, tmp_skills_source, monkeypatch
    ):
        kiro_dir = tmp_path / ".kiro"
        kiro_dir.mkdir()
        kiro_skills = kiro_dir / "skills"
        kiro_skills.mkdir()
        shutil.copytree(
            tmp_skills_source / "qa-studio",
            kiro_skills / "qa-studio",
        )

        monkeypatch.setattr("qa_studio_cli.skills.manager.KIRO_DIR", kiro_dir)
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.get_skills_directory",
            lambda: tmp_skills_source,
        )

        results = install_skills()
        already = [
            r
            for r in results
            if r.state == SkillState.INSTALLED and "Already" in r.message
        ]
        assert len(already) == 1
        assert already[0].name == "qa-studio"

    def test_warns_on_conflict_path(
        self, tmp_path, tmp_skills_source, monkeypatch
    ):
        kiro_dir = tmp_path / ".kiro"
        kiro_dir.mkdir()
        kiro_skills = kiro_dir / "skills"
        kiro_skills.mkdir()
        (kiro_skills / "qa-studio").mkdir()

        monkeypatch.setattr("qa_studio_cli.skills.manager.KIRO_DIR", kiro_dir)
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.get_skills_directory",
            lambda: tmp_skills_source,
        )

        results = install_skills()
        conflicts = [r for r in results if r.state == SkillState.CONFLICT]
        assert len(conflicts) == 1
        assert conflicts[0].name == "qa-studio"

    def test_treats_stale_symlink_as_conflict(
        self, tmp_path, tmp_skills_source, monkeypatch
    ):
        kiro_dir = tmp_path / ".kiro"
        kiro_dir.mkdir()
        kiro_skills = kiro_dir / "skills"
        kiro_skills.mkdir()
        (kiro_skills / "qa-studio").symlink_to(tmp_path / "gone")

        monkeypatch.setattr("qa_studio_cli.skills.manager.KIRO_DIR", kiro_dir)
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.get_skills_directory",
            lambda: tmp_skills_source,
        )

        results = install_skills()
        conflicts = [r for r in results if r.state == SkillState.CONFLICT]
        assert len(conflicts) == 1
        assert conflicts[0].name == "qa-studio"

    def test_returns_empty_list_when_kiro_missing(
        self, tmp_path, tmp_skills_source, monkeypatch
    ):
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_DIR", tmp_path / "no-kiro"
        )
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.get_skills_directory",
            lambda: tmp_skills_source,
        )
        results = install_skills()
        assert results == []

    def test_copies_reference_subdirectories(
        self, tmp_path, tmp_skills_source, monkeypatch
    ):
        """Install copies SKILL.md and reference/ subdirectories as real dirs."""
        kiro_dir = tmp_path / ".kiro"
        kiro_dir.mkdir()
        kiro_skills = kiro_dir / "skills"

        monkeypatch.setattr("qa_studio_cli.skills.manager.KIRO_DIR", kiro_dir)
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.get_skills_directory",
            lambda: tmp_skills_source,
        )

        results = install_skills()
        installed = [r for r in results if r.state == SkillState.INSTALLED]
        assert len(installed) == 1

        target = kiro_skills / "qa-studio"
        assert target.is_dir()
        assert not target.is_symlink()
        assert (target / "SKILL.md").is_file()
        assert (target / "reference").is_dir()
        assert not (target / "reference").is_symlink()
        assert (target / "reference" / "step-types.md").is_file()


class TestInstallSkillsLegacyCleanup:
    """Verify install_skills removes legacy skill directories."""

    def test_removes_legacy_skill_directories_on_install(
        self, tmp_path, tmp_skills_source, monkeypatch
    ):
        kiro_dir = tmp_path / ".kiro"
        kiro_dir.mkdir()
        kiro_skills = kiro_dir / "skills"
        kiro_skills.mkdir()
        # Create legacy skill directories
        for name in LEGACY_SKILL_NAMES:
            legacy = kiro_skills / name
            legacy.mkdir()
            (legacy / "SKILL.md").write_text(f"---\nname: {name}\n---\n")

        monkeypatch.setattr("qa_studio_cli.skills.manager.KIRO_DIR", kiro_dir)
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.get_skills_directory",
            lambda: tmp_skills_source,
        )

        results = install_skills()
        removed = [r for r in results if r.state == SkillState.REMOVED]
        assert len(removed) == 3
        removed_names = {r.name for r in removed}
        assert removed_names == set(LEGACY_SKILL_NAMES)
        for name in LEGACY_SKILL_NAMES:
            assert not (kiro_skills / name).exists()

    def test_removes_legacy_symlinks_on_install(
        self, tmp_path, tmp_skills_source, monkeypatch
    ):
        kiro_dir = tmp_path / ".kiro"
        kiro_dir.mkdir()
        kiro_skills = kiro_dir / "skills"
        kiro_skills.mkdir()
        # Create legacy symlinks
        for name in LEGACY_SKILL_NAMES:
            (kiro_skills / name).symlink_to(tmp_path / "gone")

        monkeypatch.setattr("qa_studio_cli.skills.manager.KIRO_DIR", kiro_dir)
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.get_skills_directory",
            lambda: tmp_skills_source,
        )

        results = install_skills()
        removed = [r for r in results if r.state == SkillState.REMOVED]
        assert len(removed) == 3
        for name in LEGACY_SKILL_NAMES:
            assert not (kiro_skills / name).exists()
            assert not (kiro_skills / name).is_symlink()

    def test_no_error_when_no_legacy_skills_exist(
        self, tmp_path, tmp_skills_source, monkeypatch
    ):
        kiro_dir = tmp_path / ".kiro"
        kiro_dir.mkdir()
        kiro_skills = kiro_dir / "skills"

        monkeypatch.setattr("qa_studio_cli.skills.manager.KIRO_DIR", kiro_dir)
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.get_skills_directory",
            lambda: tmp_skills_source,
        )

        results = install_skills()
        removed = [r for r in results if r.state == SkillState.REMOVED]
        assert len(removed) == 0


class TestUninstallSkills:
    def test_removes_copied_skill_directory(
        self, tmp_path, tmp_skills_source, monkeypatch
    ):
        kiro_skills = tmp_path / ".kiro" / "skills"
        kiro_skills.mkdir(parents=True)
        shutil.copytree(
            tmp_skills_source / "qa-studio",
            kiro_skills / "qa-studio",
        )

        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.get_skills_directory",
            lambda: tmp_skills_source,
        )

        results = uninstall_skills()
        removed = [r for r in results if r.state == SkillState.REMOVED]
        assert len(removed) == 1
        assert not (kiro_skills / "qa-studio").exists()

    def test_cleans_up_stale_symlinks(
        self, tmp_path, tmp_skills_source, monkeypatch
    ):
        kiro_skills = tmp_path / ".kiro" / "skills"
        kiro_skills.mkdir(parents=True)
        (kiro_skills / "qa-studio").symlink_to(
            tmp_skills_source / "qa-studio"
        )

        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.get_skills_directory",
            lambda: tmp_skills_source,
        )

        results = uninstall_skills()
        removed = [r for r in results if r.state == SkillState.REMOVED]
        assert len(removed) == 1
        assert not (kiro_skills / "qa-studio").exists()

    def test_skips_directory_without_skill_md(
        self, tmp_path, tmp_skills_source, monkeypatch
    ):
        kiro_skills = tmp_path / ".kiro" / "skills"
        kiro_skills.mkdir(parents=True)
        (kiro_skills / "qa-studio").mkdir()

        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.get_skills_directory",
            lambda: tmp_skills_source,
        )

        results = uninstall_skills()
        skipped = [r for r in results if r.state == SkillState.SKIPPED]
        assert len(skipped) == 1
        assert skipped[0].name == "qa-studio"
        assert (kiro_skills / "qa-studio").is_dir()

    def test_handles_no_skills_to_remove(
        self, tmp_path, tmp_skills_source, monkeypatch
    ):
        kiro_skills = tmp_path / ".kiro" / "skills"
        kiro_skills.mkdir(parents=True)

        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.get_skills_directory",
            lambda: tmp_skills_source,
        )

        results = uninstall_skills()
        assert all(r.state == SkillState.NOT_INSTALLED for r in results)


class TestUninstallSkillsLegacyCleanup:
    """Verify uninstall_skills removes legacy skill directories."""

    def test_removes_legacy_skills_on_uninstall(
        self, tmp_path, tmp_skills_source, monkeypatch
    ):
        kiro_skills = tmp_path / ".kiro" / "skills"
        kiro_skills.mkdir(parents=True)
        # Install current skill + legacy skills
        shutil.copytree(
            tmp_skills_source / "qa-studio",
            kiro_skills / "qa-studio",
        )
        for name in LEGACY_SKILL_NAMES:
            legacy = kiro_skills / name
            legacy.mkdir()
            (legacy / "SKILL.md").write_text(f"---\nname: {name}\n---\n")

        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.KIRO_SKILLS_DIR", kiro_skills
        )
        monkeypatch.setattr(
            "qa_studio_cli.skills.manager.get_skills_directory",
            lambda: tmp_skills_source,
        )

        results = uninstall_skills()
        removed = [r for r in results if r.state == SkillState.REMOVED]
        # 3 legacy + 1 current
        assert len(removed) == 4
        for name in LEGACY_SKILL_NAMES:
            assert not (kiro_skills / name).exists()
        assert not (kiro_skills / "qa-studio").exists()
