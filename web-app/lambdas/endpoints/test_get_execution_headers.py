"""Tests for get_execution_headers Lambda handler (R-API-4)."""

import json
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError


def _event(usecase_id='uc-1', execution_id='exec-1', scope='api/executions.read'):
    return {
        'pathParameters': {'id': usecase_id, 'executionId': execution_id},
        'requestContext': {
            'authorizer': {'client_id': 'test-client', 'scope': scope},
        },
    }


@pytest.fixture(autouse=True)
def _table_name(monkeypatch):
    monkeypatch.setenv('TABLE_NAME', 'test-table')


@pytest.fixture
def patched_dynamodb(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr('get_execution_headers._dynamodb', mock_client)
    return mock_client


class TestHappyPath:
    def test_returns_headers(self, patched_dynamodb):
        from get_execution_headers import handler

        patched_dynamodb.get_item.return_value = {
            'Item': {
                'pk': {'S': 'EXECUTION#exec-1'},
                'sk': {'S': 'HEADERS'},
                'headers': {
                    'M': {
                        'X-Custom': {'S': 'abc'},
                        'Authorization': {'S': 'Bearer xyz'},
                    }
                },
            }
        }

        response = handler(_event(), None)
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body == {
            'headers': {'X-Custom': 'abc', 'Authorization': 'Bearer xyz'},
        }
        kwargs = patched_dynamodb.get_item.call_args.kwargs
        assert kwargs['Key']['pk']['S'] == 'EXECUTION#exec-1'
        assert kwargs['Key']['sk']['S'] == 'HEADERS'

    def test_no_headers_record_returns_empty_map(self, patched_dynamodb):
        from get_execution_headers import handler

        patched_dynamodb.get_item.return_value = {}

        response = handler(_event(), None)
        assert response['statusCode'] == 200
        assert json.loads(response['body']) == {'headers': {}}

    def test_empty_headers_map(self, patched_dynamodb):
        from get_execution_headers import handler

        patched_dynamodb.get_item.return_value = {
            'Item': {
                'pk': {'S': 'EXECUTION#exec-1'},
                'sk': {'S': 'HEADERS'},
                'headers': {'M': {}},
            }
        }
        response = handler(_event(), None)
        assert response['statusCode'] == 200
        assert json.loads(response['body']) == {'headers': {}}


class TestAuth:
    def test_missing_scope_rejected(self, patched_dynamodb):
        from get_execution_headers import handler

        response = handler(
            _event(scope='api/executions.write'),  # write is not read
            None,
        )
        # write does not include read per the existing scope model;
        # require_scopes will reject unless admin.
        # (Admin scope trivially allows; we don't set admin here.)
        assert response['statusCode'] == 403
        patched_dynamodb.get_item.assert_not_called()


class TestValidation:
    def test_bad_path_rejected(self, patched_dynamodb):
        from get_execution_headers import handler

        response = handler(_event(execution_id='../bad'), None)
        assert response['statusCode'] == 400

    def test_missing_execution_id_rejected(self, patched_dynamodb):
        from get_execution_headers import handler

        response = handler(_event(execution_id=''), None)
        assert response['statusCode'] == 400


class TestDynamoDBError:
    def test_client_error_returns_500(self, patched_dynamodb):
        from get_execution_headers import handler

        patched_dynamodb.get_item.side_effect = ClientError(
            {'Error': {'Code': 'ThrottlingException', 'Message': 'x'}},
            'GetItem',
        )

        response = handler(_event(), None)
        assert response['statusCode'] == 500
