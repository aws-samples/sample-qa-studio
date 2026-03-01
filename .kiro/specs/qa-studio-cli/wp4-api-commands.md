# WP4: API Wrapper Commands

## Objective

Implement CLI commands for test and suite management via QA Studio API.

## Duration

Week 4-5 (5-7 days)

## Requirements

### API Client

**Create: `qa-studio-cli/src/api/client.py`**

```python
class QAStudioAPI:
    def __init__(self, token_file: str):
        self.token_file = token_file
        self.base_url = "https://api.qa-studio.com"
    
    def _get_token(self) -> str:
        """Load token from file."""
        with open(Path(self.token_file).expanduser()) as f:
            return json.load(f)['access_token']
    
    def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make authenticated API request."""
        headers = {
            'Authorization': f'Bearer {self._get_token()}',
            'Content-Type': 'application/json'
        }
        response = requests.request(
            method, f"{self.base_url}{path}", 
            headers=headers, **kwargs
        )
        response.raise_for_status()
        return response.json()
```

### Test Commands

**Create: `qa-studio-cli/src/commands/tests.py`**

Commands to implement:
- `qa-studio tests list` - List all tests
- `qa-studio tests get <id>` - Get test details
- `qa-studio tests create --from-journey` - Generate test from journey
- `qa-studio tests delete <id>` - Delete test

### Suite Commands

**Create: `qa-studio-cli/src/commands/suites.py`**

Commands to implement:
- `qa-studio suites list` - List all suites
- `qa-studio suites get <id>` - Get suite details
- `qa-studio suites create` - Create suite
- `qa-studio suites add-tests <suite-id> <usecase-ids...>` - Add tests
- `qa-studio suites remove-test <suite-id> <usecase-id>` - Remove test
- `qa-studio run-suite <id>` - Execute suite

## Success Criteria

- ✅ All commands work correctly
- ✅ API client handles authentication
- ✅ Error messages are helpful
- ✅ Commands follow CLI best practices

## Dependencies

Package 1 (auth working)

## Deliverable

Full CLI functionality for test and suite management.
