"""CLI argument parser for the CI/CD runner."""

import click
from typing import Dict, Optional


@click.command()
@click.option('--suite-id', default=None, help='Test suite ID to execute')
@click.option('--usecase-id', default=None, type=str, help='Single use case ID to execute')
@click.option('--local-only', is_flag=True, default=False, help='Local execution only (no execution records)')
@click.option('--base-url', help='Override base URL for all use cases')
@click.option('--var', 'variables', multiple=True, help='Override variable (key=value, repeatable)')
@click.option('--region', help='Override AWS region for browser')
@click.option('--model-id', help='Override Nova Act model ID')
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
@click.option('--timeout', type=int, default=3600, help='Global timeout in seconds')
@click.option('--keep-artifacts', is_flag=True, help='Keep local artifact files after upload (for debugging)')
@click.option('--output', 'output_format', type=click.Choice(['json', 'summary']), default='json', help='Output format: json (default, machine-readable) or summary (human-readable)')
def main(
    suite_id: Optional[str],
    usecase_id: Optional[str],
    local_only: bool,
    base_url: Optional[str],
    variables: tuple,
    region: Optional[str],
    model_id: Optional[str],
    verbose: bool,
    timeout: int,
    keep_artifacts: bool,
    output_format: str
):
    """Nova Act QA Studio CI/CD Runner"""

    # Validate flag combinations
    if suite_id and usecase_id:
        raise click.UsageError("--suite-id and --usecase-id are mutually exclusive")
    if not suite_id and not usecase_id:
        raise click.UsageError("Either --suite-id or --usecase-id is required")
    if local_only and not usecase_id:
        raise click.UsageError("--local-only requires --usecase-id")

    # Parse variables from key=value format
    parsed_vars: Dict[str, str] = {}
    for var in variables:
        if '=' not in var:
            raise click.BadParameter(f"Variable must be in key=value format: {var}")
        key, value = var.split('=', 1)
        parsed_vars[key] = value

    # Setup logging
    from ..utils.logger import setup_logging
    setup_logging(verbose)

    # Route to the correct execution function
    if suite_id:
        from ..main import run_runner
        run_runner(
            suite_id=suite_id,
            base_url=base_url,
            variables=parsed_vars,
            region=region,
            model_id=model_id,
            timeout=timeout,
            keep_artifacts=keep_artifacts
        )
    elif usecase_id and local_only:
        from ..main import run_usecase_local
        run_usecase_local(
            usecase_id=usecase_id,
            base_url=base_url,
            variables=parsed_vars,
            region=region,
            model_id=model_id,
            timeout=timeout,
            output_format=output_format,
        )
    else:
        # usecase_id without local_only
        from ..main import run_usecase
        run_usecase(
            usecase_id=usecase_id,
            base_url=base_url,
            variables=parsed_vars,
            region=region,
            model_id=model_id,
            timeout=timeout,
            keep_artifacts=keep_artifacts,
        )


if __name__ == '__main__':
    main()
