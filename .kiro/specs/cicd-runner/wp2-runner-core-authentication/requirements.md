# Work Package 2: Runner Core & Authentication

## Feature Information
- **Epic**: CI/CD Test Runner
- **Work Package**: WP2 - Runner Core & Authentication
- **Estimated Duration**: 5 days
- **Dependencies**: WP1a, WP1b, WP1d (API extensions and OAuth client management)
- **Status**: Not Started

---

## Overview

Build the core Python CLI application for the CI/CD runner, including OAuth client credentials authentication, token management, API client module, and CLI argument parsing. This is the foundation for the runner that will execute tests locally.

---

## User Stories

### US1: As a CI/CD runner, I need to authenticate using OAuth client credentials
**Acceptance Criteria**:
- Runner reads OAuth credentials from environment variables
- Runner authenticates using client credentials flow
- Runner receives and caches access token
- Runner refreshes token when expired
- Authentication failures provide clear error messages

### US2: As a CI/CD runner, I need to fetch test suite and usecase definitions
**Acceptance Criteria**:
- Runner can fetch test suite by ID
- Runner can fetch all usecases in a suite
- Runner can fetch usecase secrets and variables
- API client handles authentication headers
- API client retries on transient failures

### US3: As a CI/CD runner, I need to parse CLI arguments
**Acceptance Criteria**:
- Runner accepts required `--suite-id` argument
- Runner accepts optional `--base-url` argument
- Runner accepts repeatable `--var key=value` arguments
- Runner accepts `--verbose` flag for detailed logging
- Runner accepts `--timeout` argument
- Runner displays help message with `--help`

### US4: As a CI/CD runner, I need to create execution records via API
**Acceptance Criteria**:
- Runner calls `POST /api/test-suites/{id}/execute` endpoint
- Runner passes trigger_type="ci_runner"
- Runner passes all CLI overrides (base_url, variables, region, model_id)
- Runner receives suite_execution_id and list of execution_ids
- Runner handles API errors gracefully

---

## Technical Requirements

### Project Structure

```
cicd-runner/
├── src/
│   ├── __init__.py
│   ├── main.py              # CLI entry point
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── oauth_client.py  # OAuth client credentials flow
│   │   └── token_cache.py   # Token caching and refresh
│   ├── api/
│   │   ├── __init__.py
│   │   ├── client.py        # API client base
│   │   ├── test_suites.py   # Test suite API calls
│   │   ├── usecases.py      # Usecase API calls
│   │   └── executions.py    # Execution API calls
│   ├── cli/
│   │   ├── __init__.py
│   │   └── parser.py        # CLI argument parsing
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py      # Configuration management
│   └── utils/
│       ├── __init__.py
│       ├── logger.py        # Logging setup
│       └── errors.py        # Custom exceptions
├── tests/
│   ├── __init__.py
│   ├── test_auth.py
│   ├── test_api_client.py
│   └── test_cli_parser.py
├── requirements.txt
├── setup.py
└── README.md
```

### Dependencies

**requirements.txt**:
```
requests>=2.31.0
python-dotenv>=1.0.0
pydantic>=2.5.0
click>=8.1.7
```

---

## Implementation Details

### 1. OAuth Authentication

**File**: `src/auth/oauth_client.py`

```python
import requests
from datetime import datetime, timedelta
from typing import Optional
from .token_cache import TokenCache

class OAuthClient:
    """OAuth client credentials authentication."""
    
    def __init__(self, client_id: str, client_secret: str, token_endpoint: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_endpoint = token_endpoint
        self.token_cache = TokenCache()
    
    def get_access_token(self) -> str:
        """Get access token, using cache if valid."""
        # Check cache first
        cached_token = self.token_cache.get_token()
        if cached_token and not self._is_token_expired(cached_token):
            return cached_token['access_token']
        
        # Request new token
        return self._request_new_token()
    
    def _request_new_token(self) -> str:
        """Request new access token from OAuth server."""
        response = requests.post(
            self.token_endpoint,
            auth=(self.client_id, self.client_secret),
            data={
                'grant_type': 'client_credentials',
                'scope': 'api/suite.read api/suite.write api/execution.write'
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        
        if response.status_code != 200:
            raise AuthenticationError(
                f"OAuth authentication failed: {response.status_code} - {response.text}"
            )
        
        token_data = response.json()
        
        # Cache token
        self.token_cache.set_token(token_data)
        
        return token_data['access_token']
    
    def _is_token_expired(self, token_data: dict) -> bool:
        """Check if token is expired or about to expire."""
        expires_at = token_data.get('expires_at')
        if not expires_at:
            return True
        
        # Consider expired if less than 5 minutes remaining
        return datetime.utcnow() >= (expires_at - timedelta(minutes=5))
```

**File**: `src/auth/token_cache.py`

```python
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

class TokenCache:
    """Cache OAuth tokens to disk."""
    
    def __init__(self, cache_file: str = '.token_cache.json'):
        self.cache_file = Path(cache_file)
    
    def get_token(self) -> Optional[dict]:
        """Retrieve cached token."""
        if not self.cache_file.exists():
            return None
        
        try:
            with open(self.cache_file, 'r') as f:
                token_data = json.load(f)
            
            # Convert expires_at string back to datetime
            if 'expires_at' in token_data:
                token_data['expires_at'] = datetime.fromisoformat(token_data['expires_at'])
            
            return token_data
        except Exception:
            return None
    
    def set_token(self, token_data: dict) -> None:
        """Cache token to disk."""
        # Calculate expiration time
        expires_in = token_data.get('expires_in', 3600)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        cache_data = {
            'access_token': token_data['access_token'],
            'expires_at': expires_at.isoformat(),
            'expires_in': expires_in
        }
        
        with open(self.cache_file, 'w') as f:
            json.dump(cache_data, f)
    
    def clear(self) -> None:
        """Clear cached token."""
        if self.cache_file.exists():
            self.cache_file.unlink()
```

### 2. API Client

**File**: `src/api/client.py`

```python
import requests
from typing import Optional, Dict, Any
from ..auth.oauth_client import OAuthClient
from ..utils.errors import APIError

class APIClient:
    """Base API client with authentication."""
    
    def __init__(self, base_url: str, oauth_client: OAuthClient):
        self.base_url = base_url.rstrip('/')
        self.oauth_client = oauth_client
        self.session = requests.Session()
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        access_token = self.oauth_client.get_access_token()
        return {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
    
    def get(self, path: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make GET request."""
        url = f"{self.base_url}{path}"
        response = self.session.get(url, headers=self._get_headers(), params=params)
        return self._handle_response(response)
    
    def post(self, path: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make POST request."""
        url = f"{self.base_url}{path}"
        response = self.session.post(url, headers=self._get_headers(), json=data)
        return self._handle_response(response)
    
    def patch(self, path: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make PATCH request."""
        url = f"{self.base_url}{path}"
        response = self.session.patch(url, headers=self._get_headers(), json=data)
        return self._handle_response(response)
    
    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """Handle API response."""
        if response.status_code >= 400:
            raise APIError(
                f"API request failed: {response.status_code} - {response.text}",
                status_code=response.status_code,
                response=response.json() if response.text else {}
            )
        
        return response.json() if response.text else {}
```

**File**: `src/api/test_suites.py`

```python
from typing import Dict, Any, List
from .client import APIClient

class TestSuiteAPI:
    """Test suite API operations."""
    
    def __init__(self, client: APIClient):
        self.client = client
    
    def get_suite(self, suite_id: str) -> Dict[str, Any]:
        """Fetch test suite definition."""
        return self.client.get(f"/test-suites/{suite_id}")
    
    def execute_suite(
        self,
        suite_id: str,
        base_url: str = None,
        variables: Dict[str, str] = None,
        region: str = None,
        model_id: str = None
    ) -> Dict[str, Any]:
        """Execute test suite (CI/CD runner mode)."""
        payload = {
            'trigger_type': 'ci_runner'
        }
        
        if base_url:
            payload['base_url'] = base_url
        if variables:
            payload['variables'] = variables
        if region:
            payload['region'] = region
        if model_id:
            payload['model_id'] = model_id
        
        return self.client.post(f"/test-suites/{suite_id}/execute", data=payload)
```

### 3. CLI Argument Parser

**File**: `src/cli/parser.py`

```python
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
def main(suite_id: str, base_url: str, variables: tuple, region: str, model_id: str, verbose: bool, timeout: int):
    """Nova Act QA Studio CI/CD Runner"""
    
    # Parse variables from key=value format
    parsed_vars = {}
    for var in variables:
        if '=' not in var:
            raise click.BadParameter(f"Variable must be in key=value format: {var}")
        key, value = var.split('=', 1)
        parsed_vars[key] = value
    
    # Setup logging
    setup_logging(verbose)
    
    # Run runner
    from ..main import run_runner
    run_runner(
        suite_id=suite_id,
        base_url=base_url,
        variables=parsed_vars,
        region=region,
        model_id=model_id,
        timeout=timeout
    )
```

### 4. Main Runner Logic

**File**: `src/main.py`

```python
import sys
import logging
from typing import Dict, Optional
from .auth.oauth_client import OAuthClient
from .api.client import APIClient
from .api.test_suites import TestSuiteAPI
from .config.settings import Settings
from .utils.errors import RunnerError

logger = logging.getLogger(__name__)

def run_runner(
    suite_id: str,
    base_url: Optional[str],
    variables: Dict[str, str],
    region: Optional[str],
    model_id: Optional[str],
    timeout: int
):
    """Main runner execution logic."""
    try:
        # Load configuration from environment
        settings = Settings.from_env()
        
        # Initialize OAuth client
        oauth_client = OAuthClient(
            client_id=settings.oauth_client_id,
            client_secret=settings.oauth_client_secret,
            token_endpoint=settings.oauth_token_endpoint
        )
        
        # Initialize API client
        api_client = APIClient(settings.api_endpoint, oauth_client)
        test_suite_api = TestSuiteAPI(api_client)
        
        # Authenticate
        logger.info("Authenticating with OAuth client credentials...")
        oauth_client.get_access_token()
        logger.info("Successfully authenticated")
        
        # Fetch test suite
        logger.info(f"Fetching test suite: {suite_id}")
        suite = test_suite_api.get_suite(suite_id)
        logger.info(f"Found test suite: {suite['name']}")
        
        # Execute test suite
        logger.info("Creating execution records...")
        execution_response = test_suite_api.execute_suite(
            suite_id=suite_id,
            base_url=base_url,
            variables=variables,
            region=region,
            model_id=model_id
        )
        
        suite_execution_id = execution_response['suite_execution_id']
        execution_ids = execution_response['execution_ids']
        
        logger.info(f"Suite execution created: {suite_execution_id}")
        logger.info(f"Created {len(execution_ids)} execution records")
        
        # TODO: Execute tests (WP3)
        # TODO: Upload artifacts (WP4)
        # TODO: Print summary (WP3)
        
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"Runner failed: {str(e)}", exc_info=True)
        sys.exit(2)
```

---

## Configuration

### Environment Variables

**Required**:
- `OAUTH_CLIENT_ID` - OAuth client ID
- `OAUTH_CLIENT_SECRET` - OAuth client secret
- `OAUTH_TOKEN_ENDPOINT` - Cognito token endpoint URL
- `API_ENDPOINT` - Platform API base URL

**Optional**:
- `LOG_LEVEL` - Logging level (default: INFO)

---

## Testing Requirements

### Unit Tests
- Test OAuth token request and caching
- Test token expiration logic
- Test API client authentication headers
- Test CLI argument parsing
- Test variable parsing (key=value format)
- Test configuration loading from environment

### Integration Tests
- Authenticate with real OAuth credentials
- Fetch test suite via API
- Create execution records via API
- Test token refresh on expiration
- Test API error handling

---

## Success Criteria

- [ ] Runner authenticates with OAuth client credentials
- [ ] Runner caches and refreshes tokens
- [ ] Runner fetches test suite definitions
- [ ] Runner creates execution records via API
- [ ] CLI arguments parsed correctly
- [ ] Environment variables loaded
- [ ] Unit test coverage ≥ 70%
- [ ] Integration tests pass
- [ ] Error messages are clear and actionable
