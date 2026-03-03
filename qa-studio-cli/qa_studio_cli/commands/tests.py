"""Test management commands."""
import click


@click.group()
def tests():
    """Manage test cases."""
    pass


@tests.command()
def list():
    """List all tests."""
    click.echo("Test listing not yet implemented")


@tests.command()
@click.argument('test_id')
def get(test_id):
    """Get test details."""
    click.echo(f"Getting test {test_id} - not yet implemented")


@tests.command()
@click.argument('test_id')
def delete(test_id):
    """Delete a test."""
    click.echo(f"Deleting test {test_id} - not yet implemented")
