"""Browser-based OAuth authorization code grant with PKCE against Cognito."""

import base64
import hashlib
import secrets
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs

import requests

from qa_studio_cli.models.errors import AuthError
from qa_studio_cli.models.token import TokenData

CALLBACK_PORT = 19847
CALLBACK_PATH = "/callback"
FLOW_TIMEOUT_SECONDS = 120

# API scopes to request during OAuth login.
# These must match the resource server scopes defined in the CDK auth stack.
API_SCOPES = [
    "api/usecases.read",
    "api/usecases.write",
    "api/templates.read",
    "api/templates.write",
    "api/executions.read",
    "api/executions.write",
    "api/usecases.execute",
    "api/suite.read",
    "api/suite.write",
    "api/oauth-clients.read",
    "api/oauth-clients.write",
]


def generate_pkce_pair() -> tuple[str, str]:
    """
    Generate PKCE code_verifier and code_challenge (S256) per RFC 7636.

    Returns:
        Tuple of (code_verifier, code_challenge).
    """
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def exchange_code_for_tokens(
    code: str,
    code_verifier: str,
    cognito_domain: str,
    client_id: str,
) -> TokenData:
    """
    Exchange authorization code + PKCE verifier for tokens.

    Args:
        code: The authorization code from the callback.
        code_verifier: The PKCE code verifier used in the authorize request.
        cognito_domain: Cognito hosted UI domain (https://...).
        client_id: Cognito app client ID.

    Returns:
        Validated TokenData with computed expires_at.

    Raises:
        AuthError: If the token exchange fails (non-200 response).
    """
    token_url = f"{cognito_domain}/oauth2/token"
    response = requests.post(
        token_url,
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": f"http://localhost:{CALLBACK_PORT}{CALLBACK_PATH}",
            "code_verifier": code_verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if response.status_code != 200:
        raise AuthError(
            f"Token exchange failed: {response.status_code} - {response.text}"
        )

    data = response.json()
    return TokenData(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_at=int(time.time()) + data["expires_in"],
        token_type=data.get("token_type", "Bearer"),
    )


def start_oauth_flow(cognito_domain: str, client_id: str) -> TokenData:
    """
    Full browser-based OAuth authorization code grant with PKCE.

    Starts a local HTTP server, opens the browser to Cognito's authorize
    endpoint, captures the callback, and exchanges the code for tokens.

    Args:
        cognito_domain: Cognito hosted UI domain (https://...).
        client_id: Cognito app client ID.

    Returns:
        Validated TokenData with tokens from Cognito.

    Raises:
        AuthError: If the flow fails, times out, or port is in use.
    """
    code_verifier, code_challenge = generate_pkce_pair()

    # Mutable container for the authorization code captured by the callback handler
    auth_result: dict = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == CALLBACK_PATH:
                params = parse_qs(parsed.query)
                if "code" in params:
                    auth_result["code"] = params["code"][0]
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"Login successful. You can close this tab.")
                elif "error" in params:
                    auth_result["error"] = params.get(
                        "error_description", params["error"]
                    )[0]
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Login failed.")

        def log_message(self, format, *args):
            pass  # Suppress HTTP server logs

    try:
        server = HTTPServer(("localhost", CALLBACK_PORT), CallbackHandler)
    except OSError:
        raise AuthError(
            "Port 19847 is already in use. "
            "Close the application using it and try again."
        )

    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    # Build authorize URL — request OIDC + API scopes so the access token
    # contains the permissions the backend validates via require_scopes().
    all_scopes = " ".join(["openid", "profile", "email"] + API_SCOPES)
    authorize_url = f"{cognito_domain}/oauth2/authorize?" + urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": f"http://localhost:{CALLBACK_PORT}{CALLBACK_PATH}",
        "scope": all_scopes,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })

    try:
        webbrowser.open(authorize_url)
    except Exception:
        print(
            "Could not open browser. Open this URL manually:\n"
            f"{authorize_url}"
        )

    # Wait for callback with timeout
    server_thread.join(timeout=FLOW_TIMEOUT_SECONDS)
    server.server_close()

    if "error" in auth_result:
        raise AuthError(f"OAuth flow failed: {auth_result['error']}")
    if "code" not in auth_result:
        raise AuthError("OAuth flow timed out. No authorization code received.")

    # Exchange code for tokens
    return exchange_code_for_tokens(
        code=auth_result["code"],
        code_verifier=code_verifier,
        cognito_domain=cognito_domain,
        client_id=client_id,
    )
