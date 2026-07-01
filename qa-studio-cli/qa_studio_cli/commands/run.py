"""Run command — local Nova Act execution (requires qa-studio[runner] extras)."""

import click

from qa_studio_cli.runner.browser.local import list_local_browsers


@click.command()
@click.option("--suite-id", default=None, help="Test suite ID to execute")
@click.option("--usecase-id", default=None, help="Single use case ID to execute")
@click.option(
    "--execution-id", default=None,
    help=(
        "Attach to a pre-created execution record instead of creating a new "
        "one. Only valid with --usecase-id in remote (non-local-only) mode."
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
@click.option("--region", default=None, help="Override AWS region for browser")
@click.option("--model-id", default=None, help="Override Nova Act model ID")
@click.option("--device-arn", default=None, help="Override Device Farm device ARN for mobile tests")
@click.option("--app-path", default=None, help="Path to local .apk/.ipa file for mobile tests (uploads to Device Farm)")
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
    "--timeout", type=int, default=3600, help="Global timeout in seconds",
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
    local_only: bool,
    token_file: str,
    base_url: str,
    variables: tuple,
    region: str,
    model_id: str,
    device_arn: str,
    app_path: str,
    browser: str,
    cdp_endpoint_url: str,
    cdp_headers_file: str,
    local_browser: str,
    headful: bool,
    verbose: bool,
    timeout: int,
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

    # Parse variables from key=value format
    parsed_vars = {}
    for var in variables:
        if "=" not in var:
            raise click.BadParameter(
                f"Variable must be in key=value format: {var}"
            )
        key, value = var.split("=", 1)
        parsed_vars[key] = value

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
            usecase_id=usecase_id,
            local_only=local_only,
            token_file=token_file,
            base_url=base_url,
            variables=parsed_vars,
            region=region,
            model_id=model_id,
            timeout=timeout,
            output_format=output_format,
            device_arn=device_arn,
            app_path=app_path,
            execution_id=execution_id,
            browser=browser,
            cdp_endpoint_url=cdp_endpoint_url,
            cdp_headers_file=cdp_headers_file,
            local_browser=local_browser,
            headful=headful,
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
        )
