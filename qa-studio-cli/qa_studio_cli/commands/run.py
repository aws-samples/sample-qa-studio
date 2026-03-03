"""Test execution commands."""
import click


@click.command()
@click.argument('suite_id')
@click.option('--wait', is_flag=True, help='Wait for execution to complete')
@click.option('--output', type=click.Choice(['json', 'table']), default='table', help='Output format')
def run(suite_id, wait, output):
    """Execute a test suite."""
    click.echo(f"Running suite {suite_id} - not yet implemented")
    if wait:
        click.echo("Waiting for completion...")
    click.echo(f"Output format: {output}")
