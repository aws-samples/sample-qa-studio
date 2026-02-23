"""CLI argument parser for the CI/CD runner."""

import click
from typing import Dict


@click.command()
@click.option('--suite-id', required=True, help='Test suite ID to execute')
@click.option('--base-url', help='Override base URL for all use cases')
@click.option('--var', 'variables', multiple=True, help='Override variable (key=value, repeatable)')
@click.option('--region', help='Override AWS region for browser')
@click.option('--model-id', help='Override Nova Act model ID')
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
@click.option('--timeout', type=int, default=3600, help='Global timeout in seconds')
@click.option('--keep-artifacts', is_flag=True, help='Keep local artifact files after upload (for debugging)')
def main(
    suite_id: str,
    base_url: str,
    variables: tuple,
    region: str,
    model_id: str,
    verbose: bool,
    timeout: int,
    keep_artifacts: bool
):
    """Nova Act QA Studio CI/CD Runner"""
    
    # Parse variables from key=value format
    parsed_vars = {}
    for var in variables:
        if '=' not in var:
            raise click.BadParameter(f"Variable must be in key=value format: {var}")
        key, value = var.split('=', 1)
        parsed_vars[key] = value
    
    # Setup logging
    from ..utils.logger import setup_logging
    setup_logging(verbose)
    
    # Run runner
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


if __name__ == '__main__':
    main()
