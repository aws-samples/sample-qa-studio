"""Run command — local Nova Act execution (requires qa-studio[runner] extras)."""

from typing import Optional

import click

from qa_studio_cli.runner.browser.local import list_local_browsers


def _parse_usecase_ids(raw: str) -> list:
    """Split ``--usecase-id`` on whitespace; reject empty and duplicate IDs."""
    ids = raw.split()
    if not ids:
        raise click.UsageError("--usecase-id must contain at least one ID")
    seen = set()
    for uid in ids:
        if uid in seen:
            raise click.UsageError(f"--usecase-id contains a duplicate ID: {uid}")
        seen.add(uid)
    return ids


@click.command()
@click.option("--suite-id", default=None, help="Test suite ID to execute")
@click.option(
    "--usecase-id", default=None,
    help=(
        "One or more use case IDs separated by whitespace (quote the value, "
        "e.g. --usecase-id \"id-a id-b\"). Several IDs run sequentially and "
        "end with a summary."
    ),
)
@click.option(
    "--execution-id", default=None,
    help=(
        "Attach to a pre-created execution record instead of creating a new "
        "one. Only valid with exactly one --usecase-id in remote "
        "(non-local-only) mode."
    ),
)
@click.option(
    "--fail-fast", is_flag=True, default=False,
    help=(
        "Stop after the first failed use case; remaining use cases are "
        "reported as skipped. Only with --usecase-id."
    ),
)
@click.option(
    "--local-only", is_flag=True, default=False,
    help="Local-only execution (no remote records)",
)
@click.option("--token-file", default=None, help="Path to JSON token file")
@click.option("--base-url", default=None, help="Override base URL for all use cases")
@click.option(
    "--var", "variables", multiple=True,
    help="Override variable (key=value, repeatable)",
)
@click.option(
    "--dataset-file", "dataset_files", multiple=True,
    help=(
        "CSV replacing the stored rows of a repeat step for this run "
        "([LABEL=]PATH, repeatable). The header row must name the repeat's "
        "columns; LABEL is the repeat step's label and may be omitted when "
        "the use case has exactly one repeat. Only with --usecase-id."
    ),
)
@click.option(
    "--region", default=None,
    help=(
        "AWS region for the run's regional AWS calls. Local mode: the S3 "
        "app-binary download (mobile) and the browser provisioner; suite runs: "
        "the executions' region. Default: AWS_REGION / AWS profile. Nova Act "
        "always runs in us-east-1 and Device Farm in us-west-2."
    ),
)
@click.option("--model-id", default=None, help="Override Nova Act model ID")
@click.option("--device-arn", default=None, help="Override Device Farm device ARN for mobile tests")
@click.option(
    "--app-path", default=None,
    help=(
        "Application under test. Mobile: local .apk/.ipa uploaded to Device "
        "Farm. Electron: the .app bundle or executable to launch (required "
        "for electron usecases)."
    ),
)
@click.option(
    "--app-arg", "app_args", multiple=True,
    help=(
        "Extra argument for the Electron app, repeatable (e.g. the app "
        "directory when --app-path is the bare electron binary). Appended "
        "after QA Studio's own switches. Requires --app-path."
    ),
)
@click.option(
    "--app-user-data-dir",
    type=click.Path(file_okay=False, resolve_path=True),
    default=None,
    help=(
        "Electron --user-data-dir to reuse (e.g. a pre-seeded profile). "
        "Default: a fresh temp dir per run, removed at teardown. "
        "Requires --app-path."
    ),
)
@click.option(
    "--browser",
    type=click.Choice(["local", "agentcore", "cdp-external"], case_sensitive=False),
    default="local",
    help=(
        "Browser provisioner (default: local). 'agentcore' requires the "
        "[agentcore] extra; 'cdp-external' requires --cdp-endpoint-url."
    ),
)
@click.option(
    "--cdp-endpoint-url", default=None,
    help="CDP websocket URL (required when --browser=cdp-external).",
)
@click.option(
    "--cdp-headers-file",
    type=click.Path(exists=False, dir_okay=False, resolve_path=True),
    default=None,
    help=(
        "Path to a JSON file containing CDP connection headers. "
        "Delivered via file (not argv) to avoid leaking secrets."
    ),
)
@click.option(
    "--local-browser",
    type=click.Choice(list_local_browsers(), case_sensitive=False),
    default="chromium",
    help=(
        "Browser flavour for local mode. 'chromium' (default) uses "
        "NovaAct's bundled Chromium; 'chrome' uses your system Chrome "
        "with a fresh profile; 'chrome-profile' uses your system Chrome "
        "with your real user profile (cookies, sessions). "
        "Only meaningful with --browser=local."
    ),
)
@click.option(
    "--headful",
    is_flag=True,
    default=False,
    help=(
        "Run with a visible browser window. Without this the runner "
        "defers to the HEADLESS env var (default 'true' → headless) "
        "so CI behaviour stays unchanged. Only meaningful with "
        "--browser=local."
    ),
)
@click.option("--verbose", is_flag=True, help="Enable verbose logging")
@click.option(
    "--timeout", type=click.IntRange(min=1), default=None,
    help=(
        "Stop the whole run after N seconds (default: no limit). On expiry "
        "the running test fails, the rest are skipped and the exit code is 3."
    ),
)
@click.option(
    "--keep-artifacts", is_flag=True,
    help="Keep local artifact files after upload (for debugging)",
)
@click.option(
    "--format", "output_format",
    type=click.Choice(["json", "human"], case_sensitive=False),
    default="json", help="Output format (default: json)",
)
def run(
    suite_id: str,
    usecase_id: str,
    execution_id: str,
    fail_fast: bool,
    local_only: bool,
    token_file: str,
    base_url: str,
    variables: tuple,
    dataset_files: tuple,
    region: str,
    model_id: str,
    device_arn: str,
    app_path: str,
    app_args: tuple,
    app_user_data_dir: str,
    browser: str,
    cdp_endpoint_url: str,
    cdp_headers_file: str,
    local_browser: str,
    headful: bool,
    verbose: bool,
    timeout: Optional[int],
    keep_artifacts: bool,
    output_format: str,
) -> None:
    """Execute tests locally with Nova Act (requires: pip install qa-studio[runner])."""
    # Validate mutually exclusive flags
    if not suite_id and not usecase_id:
        raise click.UsageError("Either --suite-id or --usecase-id is required")
    if suite_id and usecase_id:
        raise click.UsageError("Cannot use both --suite-id and --usecase-id")
    if execution_id and not usecase_id:
        raise click.UsageError("--execution-id requires --usecase-id")
    if execution_id and suite_id:
        raise click.UsageError("--execution-id is not supported with --suite-id")
    if fail_fast and suite_id:
        raise click.UsageError("--fail-fast is only supported with --usecase-id")

    # ``--usecase-id`` carries one or more whitespace-separated IDs.
    usecase_ids = _parse_usecase_ids(usecase_id) if usecase_id else []
    if execution_id and len(usecase_ids) > 1:
        raise click.UsageError("--execution-id requires exactly one --usecase-id")

    # Validate browser-selection combinations.
    browser = (browser or "local").lower()
    if browser == "cdp-external":
        if not cdp_endpoint_url:
            raise click.UsageError(
                "--cdp-endpoint-url is required when --browser=cdp-external"
            )
    elif cdp_endpoint_url or cdp_headers_file:
        raise click.UsageError(
            "--cdp-endpoint-url and --cdp-headers-file require --browser=cdp-external"
        )

    # ``--local-browser`` is only meaningful with the local provisioner —
    # for CDP / AgentCore modes the browser is external or cloud-side,
    # so the flavour flag has no effect and silently accepting it would
    # be a footgun. Reject explicitly.
    local_browser = (local_browser or "chromium").lower()
    if local_browser != "chromium" and browser != "local":
        raise click.UsageError(
            "--local-browser is only supported with --browser=local (default)."
        )

    # ``--headful`` also only applies to the local provisioner — remote
    # browsers (AgentCore, cdp-external) don't have a visible window on
    # the user's machine to toggle.
    if headful and browser != "local":
        raise click.UsageError(
            "--headful is only supported with --browser=local (default)."
        )

    # The electron-only app flags are meaningless without an app to launch.
    if app_args and not app_path:
        raise click.UsageError("--app-arg requires --app-path")
    if app_user_data_dir and not app_path:
        raise click.UsageError("--app-user-data-dir requires --app-path")

    # Parse variables from key=value format
    parsed_vars = {}
    for var in variables:
        if "=" not in var:
            raise click.BadParameter(
                f"Variable must be in key=value format: {var}"
            )
        key, value = var.split("=", 1)
        parsed_vars[key] = value

    # Dataset overrides for repeat steps: read the CSVs now so file / shape
    # problems are usage errors before any network call.  Label resolution
    # needs the use case's steps and happens in the runner.
    if dataset_files and suite_id:
        raise click.UsageError("--dataset-file requires --usecase-id (not supported with --suite-id)")
    from qa_studio_cli.runner.dataset_file import (
        DatasetFileError, parse_dataset_file_option, read_dataset_csv,
    )
    repeat_dataset_files = []
    for raw in dataset_files:
        try:
            label, path = parse_dataset_file_option(raw)
            repeat_dataset_files.append((label, read_dataset_csv(path)))
        except DatasetFileError as exc:
            raise click.UsageError(str(exc)) from exc

    # Lazy import gate — runner extras required
    try:
        from qa_studio_cli.runner.main import run_usecase, run_runner
    except ImportError:
        click.echo(
            "Runner dependencies not installed. "
            "Run: pip install qa-studio[runner]",
            err=True,
        )
        raise SystemExit(1)

    # Setup logging
    from qa_studio_cli.utils.logger import setup_logging
    setup_logging(verbose)

    if usecase_id:
        run_usecase(
            usecase_ids=usecase_ids,
            local_only=local_only,
            fail_fast=fail_fast,
            token_file=token_file,
            base_url=base_url,
            variables=parsed_vars,
            region=region,
            model_id=model_id,
            timeout=timeout,
            output_format=output_format,
            device_arn=device_arn,
            app_path=app_path,
            app_args=list(app_args),
            app_user_data_dir=app_user_data_dir,
            execution_id=execution_id,
            browser=browser,
            cdp_endpoint_url=cdp_endpoint_url,
            cdp_headers_file=cdp_headers_file,
            local_browser=local_browser,
            headful=headful,
            repeat_dataset_files=repeat_dataset_files,
        )
    else:
        run_runner(
            suite_id=suite_id,
            local_only=local_only,
            base_url=base_url,
            variables=parsed_vars,
            region=region,
            model_id=model_id,
            timeout=timeout,
            keep_artifacts=keep_artifacts,
            token_file=token_file,
            output_format=output_format,
            local_browser=local_browser,
            headful=headful,
            app_path=app_path,
            app_args=list(app_args),
            app_user_data_dir=app_user_data_dir,
        )
