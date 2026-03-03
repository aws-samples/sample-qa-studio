"""Run command — local Nova Act execution (requires qa-studio[runner] extras)."""

import click


@click.command()
@click.option("--suite-id", default=None, help="Test suite ID to execute")
@click.option("--usecase-id", default=None, help="Single use case ID to execute")
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
    local_only: bool,
    token_file: str,
    base_url: str,
    variables: tuple,
    region: str,
    model_id: str,
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
        )
