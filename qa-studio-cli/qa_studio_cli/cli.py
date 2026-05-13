"""QA Studio CLI — authenticate and manage QA Studio from the terminal."""

import functools
import logging
from datetime import datetime

import click
from pydantic import ValidationError

from qa_studio_cli.models.config import CLIConfig
from qa_studio_cli.models.errors import AuthError
from qa_studio_cli.config.manager import save_config, load_config, config_exists, CONFIG_FILE
from qa_studio_cli.auth.token_manager import save_token, load_token, delete_token, get_valid_token, TOKEN_FILE
from qa_studio_cli.auth.oauth import start_oauth_flow
from qa_studio_cli.commands.tests import tests
from qa_studio_cli.commands.suites import suites
from qa_studio_cli.commands.run import run
from qa_studio_cli.commands.tui import tui


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
@click.option("--debug", is_flag=True, default=False, help="Enable debug logging")
@click.pass_context
def cli(ctx, debug: bool) -> None:
    """QA Studio CLI — authenticate and manage QA Studio from the terminal."""
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug
    if debug:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s: %(message)s")
        logging.getLogger("qa_studio_cli").setLevel(logging.DEBUG)


@cli.command()
def configure() -> None:
    """Interactive setup: collect API URL, Cognito domain, client ID, and optional M2M credentials."""
    click.echo("\nQA Studio CLI Configuration")
    click.echo("───────────────────────────")

    # Load existing config values as defaults if available
    existing_api_url = "https://api.qa-studio.com"
    existing_cognito_domain = "https://auth.qa-studio.com"
    existing_client_id = ""
    existing_oauth_client_id = None
    existing_oauth_client_secret = None
    existing_oauth_token_endpoint = None
    existing_web_url = None

    if config_exists():
        try:
            existing = load_config()
            existing_api_url = existing.api_url
            existing_cognito_domain = existing.cognito_domain
            existing_client_id = existing.client_id
            existing_oauth_client_id = existing.oauth_client_id
            existing_oauth_client_secret = existing.oauth_client_secret
            existing_oauth_token_endpoint = existing.oauth_token_endpoint
            existing_web_url = existing.web_url
        except Exception:
            pass  # Fall back to generic defaults

    while True:
        api_url = click.prompt("API URL", default=existing_api_url)
        cognito_domain = click.prompt("Cognito Domain", default=existing_cognito_domain)
        client_id = click.prompt("Cognito Client ID", default=existing_client_id or None)

        # Optional web-app URL (enables the TUI's "Edit in browser" action).
        click.echo("\nWeb App URL (optional — press Enter to skip)")
        web_url = click.prompt(
            "Web URL", default=existing_web_url or "", show_default=False
        ).strip() or None

        # Optional M2M credentials for CI/runner auth
        click.echo("\nM2M Authentication (optional — press Enter to skip)")
        oauth_client_id = click.prompt(
            "OAuth Client ID", default=existing_oauth_client_id or "", show_default=False
        ).strip() or None
        oauth_client_secret = click.prompt(
            "OAuth Client Secret", default=existing_oauth_client_secret or "", show_default=False
        ).strip() or None
        oauth_token_endpoint = click.prompt(
            "OAuth Token Endpoint", default=existing_oauth_token_endpoint or "", show_default=False
        ).strip() or None

        try:
            config = CLIConfig(
                api_url=api_url,
                cognito_domain=cognito_domain,
                client_id=client_id,
                web_url=web_url,
                oauth_client_id=oauth_client_id,
                oauth_client_secret=oauth_client_secret,
                oauth_token_endpoint=oauth_token_endpoint,
            )
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





cli.add_command(tests)
cli.add_command(suites)
cli.add_command(run)
cli.add_command(tui)


@cli.command()
@require_config
def status() -> None:
    """Show current authentication status."""
    try:
        get_valid_token()
        token_data = load_token()
        expires = datetime.fromtimestamp(token_data.expires_at).strftime("%Y-%m-%d %H:%M:%S")
        click.echo("✓ Authenticated")
        click.echo(f"Token expires: {expires}")
    except AuthError as e:
        click.echo(f"✗ {e.message}")
