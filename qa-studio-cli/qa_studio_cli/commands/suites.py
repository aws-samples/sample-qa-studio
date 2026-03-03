"""Test suite management commands."""
import click


@click.group()
def suites():
    """Manage test suites."""
    pass


@suites.command()
def list():
    """List all suites."""
    click.echo("Suite listing not yet implemented")


@suites.command()
@click.argument('suite_id')
def get(suite_id):
    """Get suite details."""
    click.echo(f"Getting suite {suite_id} - not yet implemented")


@suites.command()
def create():
    """Create a new suite."""
    click.echo("Suite creation not yet implemented")


@suites.command()
@click.argument('suite_id')
@click.argument('usecase_ids', nargs=-1, required=True)
def add_tests(suite_id, usecase_ids):
    """Add tests to a suite."""
    click.echo(f"Adding tests to suite {suite_id} - not yet implemented")


@suites.command()
@click.argument('suite_id')
@click.argument('usecase_id')
def remove_test(suite_id, usecase_id):
    """Remove a test from a suite."""
    click.echo(f"Removing test {usecase_id} from suite {suite_id} - not yet implemented")
