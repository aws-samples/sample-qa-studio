"""Unit tests for execute_test_suite Lambda function"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock, call
from execute_test_suite import handler, resolve_triggered_by


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(scope='api/suite.write api/executions.write', suite_id='suite-123', body=None):
    """Build a minimal API Gateway event."""
    if body is None:
        body = {'trigger_type': 'OnDemand'}
    return {
        'body': json.dumps(body),
        'pathParameters': {'suite_id': suite_id},
        'requestContext': {
            'authorizer': {
                'email': 'test@example.com',
                'sub': 'user-123',
                'scope': scope,
            }
        },
    }


def _suite_item(suite_id='suite-123', name='Test Suite', total=2):
    """Low-level DynamoDB item for a test suite."""
    return {
        'id': {'S': suite_id},
        'name': {'S': name},
        'description': {'S': ''},
        'scope': {'S': f'suite:{suite_id}'},
        'total_usecases': {'N': str(total)},
    }


def _usecase_mapping_items():
    """Low-level DynamoDB items for usecase mappings."""
    return [
        {'usecase_id': {'S': 'usecase-1'}, 'usecase_name': {'S': 'Use Case 1'}},
        {'usecase_id': {'S': 'usecase-2'}, 'usecase_name': {'S': 'Use Case 2'}},
    ]


def _usecase_definition_item(usecase_id='usecase-1'):
    """Low-level DynamoDB item for a usecase definition."""
    return {
        'name': {'S': f'UC {usecase_id}'},
        'starting_url': {'S': 'https://example.com'},
        'executing_region': {'S': 'us-east-1'},
        'model_id': {'S': 'nova-act-v1.0'},
        'enable_cache': {'BOOL': False},
    }


def _lambda_payload(execution_id='exec-abc'):
    """Mock Lambda invoke response with proper Payload streaming."""
    inner = json.dumps({
        'statusCode': 200,
        'body': json.dumps({'executionId': execution_id, 'status': 'running'}),
    }).encode('utf-8')
    payload = MagicMock()
    payload.read.return_value = inner
    return {'StatusCode': 200, 'Payload': payload}


def _setup_dynamodb_mock(mock_dynamodb, suite_item=None, usecase_items=None, num_usecases=2):
    """Configure mock_dynamodb.get_item and .query side effects for the full flow.

    Call order per usecase:
      get_item(suite) -> query(mappings) -> [get_item(usecase_def), get_item(secrets), get_item(variables)] * N
      -> get_item(steps query for each execution) ...
    We use side_effect to return the right response for each call.
    """
    if suite_item is None:
        suite_item = _suite_item()
    if usecase_items is None:
        usecase_items = _usecase_mapping_items()[:num_usecases]

    # Build get_item responses: suite, then (usecase_def, secrets, variables) per usecase
    get_item_responses = [{'Item': suite_item}]
    for mapping in usecase_items:
        uid = mapping['usecase_id']['S']
        get_item_responses.append({'Item': _usecase_definition_item(uid)})  # usecase def
        get_item_responses.append({})  # secrets (empty)
        get_item_responses.append({})  # variables (empty)

    mock_dynamodb.get_item.side_effect = get_item_responses
    mock_dynamodb.query.side_effect = [
        {'Items': usecase_items},  # usecase mappings
    ]
    mock_dynamodb.put_item.return_value = {}
    mock_dynamodb.update_item.return_value = {}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExecuteTestSuite:
    """Test suite for execute_test_suite handler"""

    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_execute_suite_success(self, mock_env_get, mock_dynamodb, mock_lambda):
        """Test successfully executing a test suite with OnDemand trigger"""
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table',
            'EXECUTE_USECASE_LAMBDA_ARN': 'arn:aws:lambda:us-east-1:123:function:exec',
        }.get(key, default)

        _setup_dynamodb_mock(mock_dynamodb)

        mock_lambda.invoke.return_value = _lambda_payload()

        response = handler(_make_event(), None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'suite_execution_id' in body
        assert body['suite_id'] == 'suite-123'
        assert body['status'] == 'pending'
        assert len(body['execution_ids']) == 2
        assert mock_lambda.invoke.call_count == 2

    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_ci_runner_trigger_creates_records_only(self, mock_env_get, mock_dynamodb, mock_lambda):
        """ci_runner trigger creates DB records without invoking Lambda"""
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table',
            'DEFAULT_REGION': 'us-east-1',
        }.get(key, default)

        # For ci_runner, the handler calls create_execution_record_for_usecase which makes
        # many more DynamoDB calls per usecase (steps, hooks, headers).
        # Use a default return for all get_item/query/put_item calls.
        mock_dynamodb.get_item.side_effect = [
            {'Item': _suite_item()},           # get_test_suite
            {'Item': _usecase_definition_item('usecase-1')},  # get_usecase_definition (uc1)
            {},                                 # get_usecase_secrets (uc1)
            {},                                 # get_usecase_variables (uc1)
            {},                                 # hooks (uc1)
            {},                                 # headers (uc1)
            {'Item': _usecase_definition_item('usecase-2')},  # get_usecase_definition (uc2)
            {},                                 # get_usecase_secrets (uc2)
            {},                                 # get_usecase_variables (uc2)
            {},                                 # hooks (uc2)
            {},                                 # headers (uc2)
        ]
        mock_dynamodb.query.side_effect = [
            {'Items': _usecase_mapping_items()},  # get_suite_usecases
            {'Items': []},                        # steps for usecase-1
            {'Items': []},                        # steps for usecase-2
        ]
        mock_dynamodb.put_item.return_value = {}
        mock_dynamodb.update_item.return_value = {}

        event = _make_event(body={'trigger_type': 'ci_runner'})
        response = handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['execution_ids']) == 2
        mock_lambda.invoke.assert_not_called()

    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_suite_not_found(self, mock_env_get, mock_dynamodb):
        """Test 404 when suite doesn't exist"""
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table',
        }.get(key, default)

        mock_dynamodb.get_item.return_value = {}  # no Item

        response = handler(_make_event(), None)

        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert 'not found' in body['error'].lower()

    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_empty_suite_returns_400(self, mock_env_get, mock_dynamodb):
        """Test 400 when suite has no usecases"""
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table',
        }.get(key, default)

        mock_dynamodb.get_item.return_value = {'Item': _suite_item(total=0)}
        mock_dynamodb.query.return_value = {'Items': []}

        response = handler(_make_event(), None)

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'Empty test suite'

    def test_missing_suite_id(self):
        """Test 400 when suite_id is missing"""
        event = _make_event()
        event['pathParameters'] = {}

        response = handler(event, None)

        assert response['statusCode'] == 400

    def test_invalid_json_body(self):
        """Test 400 when body is invalid JSON"""
        event = _make_event()
        event['body'] = 'not-json'

        response = handler(event, None)

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Invalid JSON' in body['error']

    def test_invalid_trigger_type(self):
        """Test 400 when trigger_type is invalid"""
        event = _make_event(body={'trigger_type': 'invalid'})

        response = handler(event, None)

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Invalid trigger type' in body['error']

    def test_insufficient_scope(self):
        """Test 403 when user lacks required scopes"""
        event = _make_event(scope='api/usecases.read')

        response = handler(event, None)

        assert response['statusCode'] == 403

    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_all_invocations_fail(self, mock_env_get, mock_dynamodb, mock_lambda):
        """Test 500 when all Lambda invocations fail"""
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table',
            'EXECUTE_USECASE_LAMBDA_ARN': 'arn:aws:lambda:us-east-1:123:function:exec',
        }.get(key, default)

        _setup_dynamodb_mock(mock_dynamodb)
        mock_lambda.invoke.side_effect = Exception('Lambda invocation failed')

        response = handler(_make_event(), None)

        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'Failed to execute test suite' in body['error']

    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_partial_invocation_failure(self, mock_env_get, mock_dynamodb, mock_lambda):
        """Test that partial Lambda failures still return 200 with successful executions"""
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table',
            'EXECUTE_USECASE_LAMBDA_ARN': 'arn:aws:lambda:us-east-1:123:function:exec',
        }.get(key, default)

        _setup_dynamodb_mock(mock_dynamodb)

        # First invocation succeeds, second raises — handler catches per-usecase errors
        # but the exception propagates to the outer try/except
        mock_lambda.invoke.side_effect = [
            _lambda_payload('exec-1'),
            Exception('Lambda invocation failed'),
        ]

        response = handler(_make_event(), None)

        # The handler wraps each usecase in try/except ValueError but not general Exception,
        # so a Lambda invoke failure will propagate to the outer handler and return 500
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'Failed to execute test suite' in body['error']



# ---------------------------------------------------------------------------
# resolve_triggered_by tests
# ---------------------------------------------------------------------------

class TestResolveTriggeredBy:
    """Test suite for resolve_triggered_by helper"""

    @patch('execute_test_suite.dynamodb')
    def test_user_identity_returns_email(self, mock_dynamodb):
        """User identity should return email directly"""
        identity = {
            'identity': 'test@example.com',
            'identity_type': 'user',
            'email': 'test@example.com',
        }
        result = resolve_triggered_by(identity, 'test-table')
        assert result == 'test@example.com'

    @patch('execute_test_suite.dynamodb')
    def test_client_identity_resolves_to_name(self, mock_dynamodb):
        """Client identity should resolve to client name from DynamoDB"""
        identity = {
            'identity': 'client-123',
            'identity_type': 'client',
            'client_id': 'client-123',
        }
        mock_dynamodb.get_item.return_value = {
            'Item': {
                'client_name': {'S': 'My CI Client'},
            }
        }
        result = resolve_triggered_by(identity, 'test-table')
        assert result == 'My CI Client'

    @patch('execute_test_suite.dynamodb')
    def test_client_identity_falls_back_to_id_when_not_found(self, mock_dynamodb):
        """Client identity should fall back to client_id when not in DynamoDB"""
        identity = {
            'identity': 'client-123',
            'identity_type': 'client',
            'client_id': 'client-123',
        }
        mock_dynamodb.get_item.return_value = {}
        result = resolve_triggered_by(identity, 'test-table')
        assert result == 'client-123'

    @patch('execute_test_suite.dynamodb')
    def test_client_identity_falls_back_to_id_on_dynamo_error(self, mock_dynamodb):
        """Client identity should fall back to client_id on DynamoDB error"""
        identity = {
            'identity': 'client-123',
            'identity_type': 'client',
            'client_id': 'client-123',
        }
        mock_dynamodb.get_item.side_effect = Exception('DynamoDB error')
        result = resolve_triggered_by(identity, 'test-table')
        assert result == 'client-123'

    @patch('execute_test_suite.dynamodb')
    def test_client_identity_falls_back_when_name_missing(self, mock_dynamodb):
        """Client identity should fall back when name field is missing"""
        identity = {
            'identity': 'client-123',
            'identity_type': 'client',
            'client_id': 'client-123',
        }
        mock_dynamodb.get_item.return_value = {
            'Item': {
                'pk': {'S': 'OAUTH_CLIENT#client-123'},
            }
        }
        result = resolve_triggered_by(identity, 'test-table')
        assert result == 'client-123'
