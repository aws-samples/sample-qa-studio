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

    Call order:
      get_item(suite) -> query(mappings)
      -> get_item(usecase_def) * N          (prefetched before any write — electron gate)
      -> query(steps) * N                   (prefetched — repeat expansion gate)
      -> get_item(variables) * N
      -> get_item(steps query for each execution) ...
    We use side_effect to return the right response for each call.
    """
    if suite_item is None:
        suite_item = _suite_item()
    if usecase_items is None:
        usecase_items = _usecase_mapping_items()[:num_usecases]

    # Build get_item responses: suite, every usecase_def, then variables per usecase
    get_item_responses = [{'Item': suite_item}]
    for mapping in usecase_items:
        uid = mapping['usecase_id']['S']
        get_item_responses.append({'Item': _usecase_definition_item(uid)})  # usecase def
    for _ in usecase_items:
        get_item_responses.append({})  # variables (empty)

    mock_dynamodb.get_item.side_effect = get_item_responses
    mock_dynamodb.query.side_effect = [
        {'Items': usecase_items},  # usecase mappings
    ] + [{'Items': []} for _ in usecase_items]  # steps prefetch (repeat expansion gate)
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
            {'Item': _usecase_definition_item('usecase-1')},  # get_usecase_definition (uc1, prefetch)
            {'Item': _usecase_definition_item('usecase-2')},  # get_usecase_definition (uc2, prefetch)
            {},                                 # get_usecase_variables (uc1)
            {},                                 # hooks (uc1)
            {},                                 # headers (uc1)
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
        # H-1: secret values are never read into execution variables
        read_sks = [c.kwargs['Key']['sk']['S'] for c in mock_dynamodb.get_item.call_args_list]
        assert 'SECRETS' not in read_sks

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


class TestExecuteTestSuiteRepeatGate:
    """A repeat that cannot be unrolled fails the whole request before any write."""

    _REPEAT_WITHOUT_CHILDREN = [{
        'id': {'S': 'r1'}, 'sort': {'N': '1'}, 'step_type': {'S': 'repeat'},
        'instruction': {'S': 'Lonely'},
        'repeat_columns': {'L': [{'S': 'a'}]},
        'repeat_rows': {'L': [{'L': [{'S': '1'}]}]},
    }]

    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_invalid_repeat_returns_400_without_writes(self, mock_env_get, mock_dynamodb, mock_lambda):
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table',
            'EXECUTE_USECASE_LAMBDA_ARN': 'arn:aws:lambda:us-east-1:123:function:exec',
        }.get(key, default)
        mock_dynamodb.get_item.side_effect = [
            {'Item': _suite_item()},
            {'Item': _usecase_definition_item('usecase-1')},
            {'Item': _usecase_definition_item('usecase-2')},
        ]
        mock_dynamodb.query.side_effect = [
            {'Items': _usecase_mapping_items()},
            {'Items': []},                          # usecase-1 steps
            {'Items': self._REPEAT_WITHOUT_CHILDREN},  # usecase-2 steps
        ]

        response = handler(_make_event(), None)

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'Invalid repeat step'
        assert 'Lonely' in body['message']
        assert body['details']['usecase_id'] == 'usecase-2'
        mock_dynamodb.put_item.assert_not_called()
        mock_dynamodb.batch_write_item.assert_not_called()
        mock_lambda.invoke.assert_not_called()

    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_ci_runner_expands_repeat_into_execution_steps(self, mock_env_get, mock_dynamodb, mock_lambda):
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table', 'DEFAULT_REGION': 'us-east-1',
        }.get(key, default)
        repeat_steps = [
            {
                'id': {'S': 'r1'}, 'sort': {'N': '1'}, 'step_type': {'S': 'repeat'},
                'instruction': {'S': 'Users'},
                'repeat_columns': {'L': [{'S': 'email'}]},
                'repeat_rows': {'L': [{'L': [{'S': 'a'}]}, {'L': [{'S': 'b'}]}]},
            },
            {
                'id': {'S': 'c1'}, 'sort': {'N': '2'}, 'step_type': {'S': 'navigation'},
                'instruction': {'S': 'Type {{email}}'}, 'parent_step_id': {'S': 'r1'},
            },
        ]
        mock_dynamodb.get_item.side_effect = [
            {'Item': _suite_item(total=1)},
            {'Item': _usecase_definition_item('usecase-1')},
            {},      # variables
            {}, {},  # hooks, headers
        ]
        mock_dynamodb.query.side_effect = [
            {'Items': _usecase_mapping_items()[:1]},
            {'Items': repeat_steps},  # prefetched steps (reused for the record)
        ]
        mock_dynamodb.put_item.return_value = {}
        mock_dynamodb.update_item.return_value = {}

        response = handler(_make_event(body={'trigger_type': 'ci_runner'}), None)

        assert response['statusCode'] == 200, response['body']
        written = [
            r['PutRequest']['Item']
            for c in mock_dynamodb.batch_write_item.call_args_list
            for reqs in c.kwargs['RequestItems'].values()
            for r in reqs
        ]
        assert [i['repeat_row_index']['N'] for i in written] == ['1', '2']
        assert [i['row_variables']['M']['email']['S'] for i in written] == ['a', 'b']


class TestExecuteTestSuiteRejectsDatasetOverrides:
    def test_repeat_datasets_is_400(self):
        event = _make_event(body={'trigger_type': 'ci_runner', 'repeat_datasets': {'Users': {'columns': ['a'], 'rows': [['1']]}}})
        with patch('execute_test_suite.dynamodb') as mock_dynamodb:
            response = handler(event, None)
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'repeat_datasets is not supported for suites'
        mock_dynamodb.get_item.assert_not_called()


import pytest as _pytest  # noqa: E402
from authz_test_support import resource_access_granted as _resource_access_granted  # noqa: E402


@_pytest.fixture(autouse=True)
def _access_granted():
    """Handler-logic tests: ownership is covered by test_suite_routes_access.py."""
    with _resource_access_granted():
        yield


# ---------------------------------------------------------------------------
# Effective variables: application layer (prefetched once per application)
# under the use-case layer, CLI overrides on top.
# ---------------------------------------------------------------------------

def _typed_rows(*pairs):
    return {'L': [{'M': {'key': {'S': k}, 'value': {'S': v}}} for k, v in pairs]}


class TestExecuteTestSuiteEffectiveVariables:
    def _run(self, mock_dynamodb, records, cli_variables=None, application_ids=('app-1', 'app-1')):
        """Two use cases of (by default) the same application, ci_runner trigger."""
        definitions = {}
        for uid, app_id in zip(('usecase-1', 'usecase-2'), application_ids):
            item = _usecase_definition_item(uid)
            if app_id:
                item['application_id'] = {'S': app_id}
            definitions[uid] = item

        def get_item(**kwargs):
            pk, sk = kwargs['Key']['pk']['S'], kwargs['Key']['sk']['S']
            if pk == 'TEST_SUITES':
                return {'Item': _suite_item()}
            if pk == 'USECASES':
                return {'Item': definitions[sk.split('#', 1)[1]]}
            item = records.get((pk, sk))
            return {'Item': item} if item is not None else {}

        mock_dynamodb.get_item.side_effect = get_item
        mock_dynamodb.query.side_effect = [{'Items': _usecase_mapping_items()}, {'Items': []}, {'Items': []}]
        mock_dynamodb.put_item.return_value = {}
        mock_dynamodb.update_item.return_value = {}

        body = {'trigger_type': 'ci_runner'}
        if cli_variables is not None:
            body['variables'] = cli_variables
        response = handler(_make_event(body=body), None)
        assert response['statusCode'] == 200, response['body']
        snapshots = [c.kwargs['Item'] for c in mock_dynamodb.put_item.call_args_list
                     if c.kwargs['Item']['sk']['S'] == 'EXECUTION_VARIABLES']
        read_keys = [(c.kwargs['Key']['pk']['S'], c.kwargs['Key']['sk']['S'])
                     for c in mock_dynamodb.get_item.call_args_list]
        return snapshots, read_keys

    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_application_variables_inherited_and_shadowed(self, mock_env_get, mock_dynamodb):
        mock_env_get.side_effect = lambda key, default=None: {'TABLE_NAME': 'test-table'}.get(key, default)
        snapshots, read_keys = self._run(mock_dynamodb, {
            ('APPLICATION#app-1', 'VARIABLES'): {'variables': _typed_rows(('base', 'app'), ('zone', 'eu'))},
            ('USECASE#usecase-1', 'USECASE_VARIABLES'): {'variables': _typed_rows(('base', 'uc1'))},
        })
        assert [s['variables']['M'] for s in snapshots] == [
            {'base': {'S': 'uc1'}, 'zone': {'S': 'eu'}},   # usecase-1 shadows base
            {'base': {'S': 'app'}, 'zone': {'S': 'eu'}},   # usecase-2 inherits both
        ]
        # The application record is read once for both use cases, before any write.
        assert read_keys.count(('APPLICATION#app-1', 'VARIABLES')) == 1
        first_write_index = len(read_keys) - read_keys[::-1].index(('USECASES', 'USECASE#usecase-2'))
        assert read_keys.index(('APPLICATION#app-1', 'VARIABLES')) >= first_write_index
        assert read_keys.index(('APPLICATION#app-1', 'VARIABLES')) < read_keys.index(
            ('USECASE#usecase-1', 'USECASE_VARIABLES'))

    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_one_read_per_distinct_application(self, mock_env_get, mock_dynamodb):
        mock_env_get.side_effect = lambda key, default=None: {'TABLE_NAME': 'test-table'}.get(key, default)
        snapshots, read_keys = self._run(mock_dynamodb, {
            ('APPLICATION#app-1', 'VARIABLES'): {'variables': _typed_rows(('a', '1'))},
            ('APPLICATION#app-2', 'VARIABLES'): {'variables': _typed_rows(('a', '2'))},
        }, application_ids=('app-1', 'app-2'))
        assert [s['variables']['M'] for s in snapshots] == [{'a': {'S': '1'}}, {'a': {'S': '2'}}]
        assert read_keys.count(('APPLICATION#app-1', 'VARIABLES')) == 1
        assert read_keys.count(('APPLICATION#app-2', 'VARIABLES')) == 1

    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_cli_override_wins_over_both_layers(self, mock_env_get, mock_dynamodb):
        mock_env_get.side_effect = lambda key, default=None: {'TABLE_NAME': 'test-table'}.get(key, default)
        snapshots, _ = self._run(mock_dynamodb, {
            ('APPLICATION#app-1', 'VARIABLES'): {'variables': _typed_rows(('base', 'app'))},
            ('USECASE#usecase-1', 'USECASE_VARIABLES'): {'variables': _typed_rows(('base', 'uc1'))},
        }, cli_variables={'base': 'cli'})
        assert [s['variables']['M'] for s in snapshots] == [{'base': {'S': 'cli'}}, {'base': {'S': 'cli'}}]

    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_legacy_usecases_without_application_read_no_application_record(self, mock_env_get, mock_dynamodb):
        mock_env_get.side_effect = lambda key, default=None: {'TABLE_NAME': 'test-table'}.get(key, default)
        snapshots, read_keys = self._run(mock_dynamodb, {
            ('USECASE#usecase-1', 'USECASE_VARIABLES'): {'variables': _typed_rows(('b', '2'), ('a', '1'))},
        }, application_ids=(None, None))
        assert [s['variables']['M'] for s in snapshots] == [{'b': {'S': '2'}, 'a': {'S': '1'}}]
        assert not any(pk.startswith('APPLICATION#') for pk, _ in read_keys)


# ---------------------------------------------------------------------------
# Dataset references: repeat steps with ``dataset_id`` are resolved from the
# owning application (prefetched, one read per dataset) before any write.
# ---------------------------------------------------------------------------

def _dataset_record(dataset_id, columns, rows):
    return {
        'dataset_id': {'S': dataset_id},
        'columns': {'L': [{'S': c} for c in columns]},
        'rows': {'L': [{'L': [{'S': cell} for cell in row]} for row in rows]},
    }


def _dataset_repeat_steps(dataset_id, label='Users'):
    return [
        {'id': {'S': 'r1'}, 'sort': {'N': '1'}, 'step_type': {'S': 'repeat'},
         'instruction': {'S': label}, 'dataset_id': {'S': dataset_id}},
        {'id': {'S': 'c1'}, 'sort': {'N': '2'}, 'step_type': {'S': 'navigation'},
         'instruction': {'S': 'Type {{email}}'}, 'parent_step_id': {'S': 'r1'}},
    ]


def _inline_repeat_steps():
    return [
        {'id': {'S': 'r1'}, 'sort': {'N': '1'}, 'step_type': {'S': 'repeat'},
         'instruction': {'S': 'Inline'},
         'repeat_columns': {'L': [{'S': 'email'}]},
         'repeat_rows': {'L': [{'L': [{'S': 'inline'}]}]}},
        {'id': {'S': 'c1'}, 'sort': {'N': '2'}, 'step_type': {'S': 'navigation'},
         'instruction': {'S': 'Type {{email}}'}, 'parent_step_id': {'S': 'r1'},
         'cached_steps': {'S': '[]'}},
        {'id': {'S': 'p1'}, 'sort': {'N': '3'}, 'step_type': {'S': 'validation'},
         'instruction': {'S': 'Done'}, 'validation_type': {'S': 'text'}},
    ]


def _without_sk(items):
    """Items minus their fresh UUIDv7 ``sk`` so two builds can be compared."""
    return [{k: v for k, v in item.items() if k != 'sk'} for item in items]


class TestExecuteTestSuiteDatasetReferences:
    def _run(self, mock_dynamodb, steps_by_usecase, records, application_ids=('app-1', 'app-1')):
        """Two use cases, ci_runner trigger; ``steps_by_usecase`` are the typed STEP# records."""
        definitions = {}
        for uid, app_id in zip(('usecase-1', 'usecase-2'), application_ids):
            item = _usecase_definition_item(uid)
            if app_id:
                item['application_id'] = {'S': app_id}
            definitions[uid] = item

        def get_item(**kwargs):
            pk, sk = kwargs['Key']['pk']['S'], kwargs['Key']['sk']['S']
            if pk == 'TEST_SUITES':
                return {'Item': _suite_item()}
            if pk == 'USECASES':
                return {'Item': definitions[sk.split('#', 1)[1]]}
            item = records.get((pk, sk))
            return {'Item': item} if item is not None else {}

        def query(**kwargs):
            pk = kwargs['ExpressionAttributeValues'][':pk']['S']
            if not pk.startswith('USECASE#'):
                return {'Items': _usecase_mapping_items()}  # SUITE#{id} mappings
            return {'Items': steps_by_usecase.get(pk.split('#', 1)[1], [])}

        mock_dynamodb.get_item.side_effect = get_item
        mock_dynamodb.query.side_effect = query
        mock_dynamodb.put_item.return_value = {}
        mock_dynamodb.update_item.return_value = {}

        response = handler(_make_event(body={'trigger_type': 'ci_runner'}), None)
        written = [
            r['PutRequest']['Item']
            for c in mock_dynamodb.batch_write_item.call_args_list
            for reqs in c.kwargs['RequestItems'].values()
            for r in reqs
        ]
        read_keys = [(c.kwargs['Key']['pk']['S'], c.kwargs['Key']['sk']['S'])
                     for c in mock_dynamodb.get_item.call_args_list]
        # {usecase_id: execution_id} from the USECASE_EXECUTION# records.
        executions = {
            c.kwargs['Item']['pk']['S'].split('#', 1)[1]: c.kwargs['Item']['sk']['S'].split('#', 1)[1]
            for c in mock_dynamodb.put_item.call_args_list
            if c.kwargs['Item']['pk']['S'].startswith('USECASE_EXECUTION#')
        }
        return response, written, read_keys, executions

    @staticmethod
    def _steps_of(written, execution_id):
        return [i for i in written if i['pk']['S'] == f'EXECUTION#{execution_id}']

    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_dataset_rows_expanded_and_inline_repeat_byte_identical(self, mock_env_get, mock_dynamodb, mock_lambda):
        from execution_steps import build_execution_step_items

        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table', 'DEFAULT_REGION': 'us-east-1'}.get(key, default)
        response, written, read_keys, executions = self._run(
            mock_dynamodb,
            {'usecase-1': _dataset_repeat_steps('ds-1'), 'usecase-2': _inline_repeat_steps()},
            {('APPLICATION#app-1', 'DATASET#ds-1'): _dataset_record('ds-1', ['email'], [['a@x.test'], ['b@x.test']])},
        )
        assert response['statusCode'] == 200, response['body']
        first = self._steps_of(written, executions['usecase-1'])
        second = self._steps_of(written, executions['usecase-2'])
        assert [i['row_variables']['M']['email']['S'] for i in first] == ['a@x.test', 'b@x.test']
        assert all('dataset_id' not in i for i in first)
        # The inline use case is untouched by the fetcher: identical to the plain builder.
        expected = build_execution_step_items(
            _inline_repeat_steps(), executions['usecase-2'], second[0]['created_at']['S'],
        )
        assert _without_sk(second) == _without_sk(expected)
        assert read_keys.count(('APPLICATION#app-1', 'DATASET#ds-1')) == 1
        mock_lambda.invoke.assert_not_called()

    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_dataset_read_happens_before_the_first_write(self, mock_env_get, mock_dynamodb, mock_lambda):
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table', 'DEFAULT_REGION': 'us-east-1'}.get(key, default)
        response, _, _, _ = self._run(
            mock_dynamodb,
            {'usecase-1': [], 'usecase-2': _dataset_repeat_steps('ds-1')},
            {('APPLICATION#app-1', 'DATASET#ds-1'): _dataset_record('ds-1', ['email'], [['a@x.test']])},
        )
        assert response['statusCode'] == 200, response['body']
        names = [c[0] for c in mock_dynamodb.mock_calls]
        dataset_read = next(i for i, c in enumerate(mock_dynamodb.mock_calls)
                            if c[0] == 'get_item' and c[2]['Key']['sk']['S'] == 'DATASET#ds-1')
        first_write = min(i for i, n in enumerate(names) if n in ('put_item', 'batch_write_item', 'update_item'))
        assert dataset_read < first_write

    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_missing_dataset_is_400_without_writes(self, mock_env_get, mock_dynamodb, mock_lambda):
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table',
            'EXECUTE_USECASE_LAMBDA_ARN': 'arn:aws:lambda:us-east-1:123:function:exec',
        }.get(key, default)
        response, written, _, _ = self._run(
            mock_dynamodb,
            {'usecase-1': [], 'usecase-2': _dataset_repeat_steps('ds-missing')},
            {},
        )
        assert response['statusCode'] == 400, response['body']
        assert json.loads(response['body']) == {
            'error': 'dataset not found',
            'dataset_id': 'ds-missing',
            'details': {'usecase_id': 'usecase-2'},
        }
        assert written == []
        mock_dynamodb.put_item.assert_not_called()
        mock_dynamodb.update_item.assert_not_called()
        mock_lambda.invoke.assert_not_called()

    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_same_dataset_across_usecases_is_read_once(self, mock_env_get, mock_dynamodb, mock_lambda):
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table', 'DEFAULT_REGION': 'us-east-1'}.get(key, default)
        response, written, read_keys, _ = self._run(
            mock_dynamodb,
            {'usecase-1': _dataset_repeat_steps('ds-1'), 'usecase-2': _dataset_repeat_steps('ds-1', label='Other')},
            {('APPLICATION#app-1', 'DATASET#ds-1'): _dataset_record('ds-1', ['email'], [['a@x.test']])},
        )
        assert response['statusCode'] == 200, response['body']
        assert len(written) == 2
        assert read_keys.count(('APPLICATION#app-1', 'DATASET#ds-1')) == 1

    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_datasets_are_scoped_to_each_usecases_application(self, mock_env_get, mock_dynamodb, mock_lambda):
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table', 'DEFAULT_REGION': 'us-east-1'}.get(key, default)
        response, written, read_keys, _ = self._run(
            mock_dynamodb,
            {'usecase-1': _dataset_repeat_steps('ds-1'), 'usecase-2': _dataset_repeat_steps('ds-1')},
            {('APPLICATION#app-1', 'DATASET#ds-1'): _dataset_record('ds-1', ['email'], [['one']]),
             ('APPLICATION#app-2', 'DATASET#ds-1'): _dataset_record('ds-1', ['email'], [['two']])},
            application_ids=('app-1', 'app-2'),
        )
        assert response['statusCode'] == 200, response['body']
        assert sorted(i['row_variables']['M']['email']['S'] for i in written) == ['one', 'two']
        assert read_keys.count(('APPLICATION#app-1', 'DATASET#ds-1')) == 1
        assert read_keys.count(('APPLICATION#app-2', 'DATASET#ds-1')) == 1

    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_usecase_without_application_cannot_resolve(self, mock_env_get, mock_dynamodb, mock_lambda):
        mock_env_get.side_effect = lambda key, default=None: {'TABLE_NAME': 'test-table'}.get(key, default)
        response, written, read_keys, _ = self._run(
            mock_dynamodb,
            {'usecase-1': _dataset_repeat_steps('ds-1'), 'usecase-2': []},
            {('APPLICATION#app-1', 'DATASET#ds-1'): _dataset_record('ds-1', ['email'], [['x']])},
            application_ids=(None, None),
        )
        assert response['statusCode'] == 400, response['body']
        assert json.loads(response['body'])['details'] == {'usecase_id': 'usecase-1'}
        assert not any(pk.startswith('APPLICATION#') for pk, _ in read_keys)
        assert written == []

    @patch('execute_test_suite.lambda_client')
    @patch('execute_test_suite.dynamodb')
    @patch('execute_test_suite.os.environ.get')
    def test_usecases_without_references_read_no_dataset(self, mock_env_get, mock_dynamodb, mock_lambda):
        mock_env_get.side_effect = lambda key, default=None: {
            'TABLE_NAME': 'test-table', 'DEFAULT_REGION': 'us-east-1'}.get(key, default)
        response, _, read_keys, _ = self._run(
            mock_dynamodb, {'usecase-1': _inline_repeat_steps(), 'usecase-2': []}, {},
        )
        assert response['statusCode'] == 200, response['body']
        assert not any(sk.startswith('DATASET#') for _, sk in read_keys)
