"""Unit tests for CLI skill commands (setup, uninstall, enhanced status)."""

from unittest.mock import patch

from click.testing import CliRunner

from qa_studio_cli.cli import cli
from qa_studio_cli.models.skills import SkillState, SkillStatus


def _make_status(name, state, message=""):
    return SkillStatus(name=name, state=state, message=message)


class TestSetupCommand:
    def test_installs_skills_when_kiro_present(self):
        results = [
            _make_status("qa-studio-tests", SkillState.INSTALLED, "Installed qa-studio-tests"),
            _make_status("qa-studio-suites", SkillState.INSTALLED, "Installed qa-studio-suites"),
        ]
        with patch("qa_studio_cli.cli.is_kiro_installed", return_value=True), \
             patch("qa_studio_cli.cli.install_skills", return_value=results):
            runner = CliRunner()
            result = runner.invoke(cli, ["setup"])
            assert result.exit_code == 0
            assert "Installed qa-studio-tests" in result.output
            assert "Installed qa-studio-suites" in result.output
            assert "2 skill(s) installed" in result.output

    def test_warns_when_kiro_not_installed(self):
        with patch("qa_studio_cli.cli.is_kiro_installed", return_value=False):
            runner = CliRunner()
            result = runner.invoke(cli, ["setup"])
            assert result.exit_code == 0
            assert "Kiro IDE not detected" in result.output

    def test_shows_already_installed(self):
        results = [
            _make_status("qa-studio-tests", SkillState.INSTALLED, "Already installed"),
            _make_status("qa-studio-suites", SkillState.INSTALLED, "Already installed"),
        ]
        with patch("qa_studio_cli.cli.is_kiro_installed", return_value=True), \
             patch("qa_studio_cli.cli.install_skills", return_value=results):
            runner = CliRunner()
            result = runner.invoke(cli, ["setup"])
            assert result.exit_code == 0
            assert "already installed" in result.output.lower()

    def test_shows_conflict_warning(self):
        results = [
            _make_status(
                "qa-studio-tests",
                SkillState.CONFLICT,
                "qa-studio-tests exists but is not a valid skill — skipped",
            ),
            _make_status("qa-studio-suites", SkillState.INSTALLED, "Installed qa-studio-suites"),
        ]
        with patch("qa_studio_cli.cli.is_kiro_installed", return_value=True), \
             patch("qa_studio_cli.cli.install_skills", return_value=results):
            runner = CliRunner()
            result = runner.invoke(cli, ["setup"])
            assert result.exit_code == 0
            assert "not a valid skill" in result.output


class TestUninstallCommand:
    def test_removes_installed_skills(self):
        results = [
            _make_status("qa-studio-tests", SkillState.REMOVED, "Removed qa-studio-tests"),
            _make_status("qa-studio-suites", SkillState.REMOVED, "Removed qa-studio-suites"),
        ]
        with patch("qa_studio_cli.cli.uninstall_skills", return_value=results):
            runner = CliRunner()
            result = runner.invoke(cli, ["uninstall"])
            assert result.exit_code == 0
            assert "Removed qa-studio-tests" in result.output
            assert "2 skill(s) removed" in result.output

    def test_shows_no_skills_to_remove(self):
        results = [
            _make_status("qa-studio-tests", SkillState.NOT_INSTALLED, "Not installed"),
            _make_status("qa-studio-suites", SkillState.NOT_INSTALLED, "Not installed"),
        ]
        with patch("qa_studio_cli.cli.uninstall_skills", return_value=results):
            runner = CliRunner()
            result = runner.invoke(cli, ["uninstall"])
            assert result.exit_code == 0
            assert "No skills to remove" in result.output

    def test_skips_non_symlink_paths(self):
        results = [
            _make_status("qa-studio-tests", SkillState.SKIPPED, "not a valid skill"),
        ]
        with patch("qa_studio_cli.cli.uninstall_skills", return_value=results):
            runner = CliRunner()
            result = runner.invoke(cli, ["uninstall"])
            assert result.exit_code == 0
            assert "not a valid skill" in result.output


class TestStatusCommand:
    def _mock_auth(self):
        """Return context managers that mock auth for the status command."""
        return (
            patch("qa_studio_cli.cli.config_exists", return_value=True),
            patch("qa_studio_cli.cli.get_valid_token", return_value="tok"),
            patch(
                "qa_studio_cli.cli.load_token",
                return_value=type("T", (), {
                    "expires_at": 1999999999,
                    "access_token": "tok",
                })(),
            ),
        )

    def test_shows_skills_with_checkmarks(self):
        statuses = [
            _make_status("qa-studio-tests", SkillState.INSTALLED),
            _make_status("qa-studio-suites", SkillState.INSTALLED),
        ]
        p1, p2, p3 = self._mock_auth()
        with p1, p2, p3, \
             patch("qa_studio_cli.cli.check_all_skills_status", return_value=statuses):
            runner = CliRunner()
            result = runner.invoke(cli, ["status"])
            assert result.exit_code == 0
            assert "Skills:" in result.output
            assert "✓ qa-studio-tests" in result.output
            assert "✓ qa-studio-suites" in result.output

    def test_shows_not_installed_with_cross(self):
        statuses = [
            _make_status("qa-studio-tests", SkillState.NOT_INSTALLED),
            _make_status("qa-studio-suites", SkillState.INSTALLED),
        ]
        p1, p2, p3 = self._mock_auth()
        with p1, p2, p3, \
             patch("qa_studio_cli.cli.check_all_skills_status", return_value=statuses):
            runner = CliRunner()
            result = runner.invoke(cli, ["status"])
            assert result.exit_code == 0
            assert "✗ qa-studio-tests (not installed)" in result.output
            assert "qa-studio setup" in result.output

    def test_shows_config_error_without_config(self):
        with patch("qa_studio_cli.cli.config_exists", return_value=False):
            runner = CliRunner()
            result = runner.invoke(cli, ["status"])
            assert "Configuration not found" in result.output
