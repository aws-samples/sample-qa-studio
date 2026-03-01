"""QA Studio CLI — authenticate and manage QA Studio from the terminal."""

import functools
from datetime import datetime

import click
from pydantic import ValidationError

from qa_studio_cli.models.config import CLIConfig
from qa_studio_cli.models.errors import AuthError
from qa_studio_cli.utils.config import save_config, load_config, config_exists, CONFIG_FILE
from qa_studio_cli.auth.token_manager import save_token, load_token, delete_token, get_valid_token, TOKEN_FILE
from qa_studio_cli.auth.oauth import start_oauth_flow


def require_config(fn):
    """Decorator that guards on config existence before executing the wrapped function."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not config_exists():
            click.echo("Configuration not found. Run 'qa-studio configure' first.")
            raise SystemExit(1)
        return fn(*args, **kwargs)
    return wrapper


@click.group()
def cli() -> None:
    """QA Studio CLI — authenticate and manage QA Studio from the terminal."""
    pass


@cli.command()
def configure() -> None:
    """Interactive setup: collect API URL, Cognito domain, client ID."""
    click.echo("\nQA Studio CLI Configuration")
    click.echo("───────────────────────────")

    while True:
        api_url = click.prompt("API URL", default="https://api.qa-studio.com")
        cognito_domain = click.prompt("Cognito Domain", default="https://auth.qa-studio.com")
        client_id = click.prompt("Cognito Client ID")

        try:
            config = CLIConfig(api_url=api_url, cognito_domain=cognito_domain, client_id=client_id)
            break
        except ValidationError as e:
            click.echo(f"\nValidation error: {e}")
            click.echo("Please try again.\n")

    save_config(config)
    click.echo(f"\n✓ Configuration saved to {CONFIG_FILE}")


@cli.command()
@require_config
def login() -> None:
    """Start browser-based OAuth flow and store tokens."""
    config = load_config()
    click.echo("Opening browser for authentication...")

    try:
        token_response = start_oauth_flow(
            cognito_domain=config.cognito_domain,
            client_id=config.client_id,
        )
        save_token(token_response)
        click.echo("✓ Logged in successfully")
        click.echo(f"Token saved to {TOKEN_FILE}")
    except AuthError as e:
        click.echo(e.message)


@cli.command()
@require_config
def logout() -> None:
    """Delete stored tokens."""
    delete_token()
    click.echo("✓ Logged out successfully")


@cli.command()
@require_config
def status() -> None:
    """Show current authentication state."""
    try:
        get_valid_token()
        token_data = load_token()
        expires = datetime.fromtimestamp(token_data.expires_at).strftime("%Y-%m-%d %H:%M:%S")
        click.echo("✓ Authenticated")
        click.echo(f"Token expires: {expires}")
    except AuthError as e:
        click.echo(f"✗ {e.message}")
