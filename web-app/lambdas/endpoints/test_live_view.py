"""Tests for create_live_view and delete_live_view Lambda handlers.

Validates requirement R-API-2 in
``.kiro/specs/cli-unified-runner/requirements.md``.
"""
import json
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError


def _event(
    body=None,
    usecase_id='uc-1',
    execution_id='exec-1',
    scope='api/executions.write',
):
    event = {
        'pathParameters': {'id': usecase_id, 'executionId': execution_id},
        'requestContext': {
            'authorizer': {
                'client_id': 'test-client',
                'scope': scope,
            },
        },
    }
    if body is not None:
        event['body'] = json.dumps(body)
    return event


@pytest.fixture(autouse=True)
def _table_name(monkeypatch):
    monkeypatch.setenv('TABLE_NAME', 'test-table')


# ---------------------------------------------------------------------------
# create_live_view
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_create_dynamodb(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr('create_live_view._dynamodb', mock_client)
    return mock_client


class TestCreateLiveView:
    def test_happy_path(self, patched_create_dynamodb):
        from create_live_view import handler

        patched_create_dynamodb.put_item.return_value = {}

        response = handler(
            _event({'live_view_url': 'https://live.example/session/abc'}), None,
        )

        assert response['statusCode'] == 200
        assert json.loads(response['body']) == {'status': 'ok'}
        patched_create_dynamodb.put_item.assert_called_once()
        item = patched_create_dynamodb.put_item.call_args.kwargs['Item']
        assert item['pk']['S'] == 'EXECUTION#exec-1'
        assert item['sk']['S'] == 'LIVE_VIEW'
        assert item['live_view_url']['S'] == 'https://live.example/session/abc'
        assert 'created_at' in item

    def test_missing_scope_rejected(self, patched_create_dynamodb):
        from create_live_view import handler

        response = handler(
            _event(
                {'live_view_url': 'https://x.test/'}, scope='api/executions.read',
            ),
            None,
        )
        assert response['statusCode'] == 403
        patched_create_dynamodb.put_item.assert_not_called()

    def test_missing_body_rejected(self, patched_create_dynamodb):
        from create_live_view import handler

        response = handler(_event(body=None), None)
        assert response['statusCode'] == 400

    def test_missing_url_rejected(self, patched_create_dynamodb):
        from create_live_view import handler

        response = handler(_event({}), None)
        assert response['statusCode'] == 400

    def test_non_string_url_rejected(self, patched_create_dynamodb):
        from create_live_view import handler

        response = handler(_event({'live_view_url': 123}), None)
        assert response['statusCode'] == 400

    def test_oversized_url_rejected(self, patched_create_dynamodb):
        from create_live_view import handler

        response = handler(
            _event({'live_view_url': 'https://x.test/' + ('a' * 3000)}), None,
        )
        assert response['statusCode'] == 400

    def test_bad_scheme_rejected(self, patched_create_dynamodb):
        from create_live_view import handler

        response = handler(_event({'live_view_url': 'file:///etc/passwd'}), None)
        assert response['statusCode'] == 400
        assert 'scheme' in json.loads(response['body'])['error'].lower()

    def test_no_host_rejected(self, patched_create_dynamodb):
        from create_live_view import handler

        response = handler(_event({'live_view_url': 'http:///path'}), None)
        assert response['statusCode'] == 400

    def test_bad_execution_id_rejected(self, patched_create_dynamodb):
        from create_live_view import handler

        response = handler(
            _event(
                {'live_view_url': 'https://x.test/'},
                execution_id='../traversal',
            ),
            None,
        )
        assert response['statusCode'] == 400

    def test_dynamodb_error_returns_500(self, patched_create_dynamodb):
        from create_live_view import handler

        patched_create_dynamodb.put_item.side_effect = ClientError(
            {'Error': {'Code': 'ThrottlingException', 'Message': 'x'}},
            'PutItem',
        )

        response = handler(_event({'live_view_url': 'https://x.test/'}), None)
        assert response['statusCode'] == 500


# ---------------------------------------------------------------------------
# delete_live_view
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_delete_dynamodb(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr('delete_live_view._dynamodb', mock_client)
    return mock_client


class TestDeleteLiveView:
    def test_happy_path_returns_204(self, patched_delete_dynamodb):
        from delete_live_view import handler

        patched_delete_dynamodb.delete_item.return_value = {}

        response = handler(_event(), None)
        assert response['statusCode'] == 204
        patched_delete_dynamodb.delete_item.assert_called_once()
        kwargs = patched_delete_dynamodb.delete_item.call_args.kwargs
        assert kwargs['Key']['pk']['S'] == 'EXECUTION#exec-1'
        assert kwargs['Key']['sk']['S'] == 'LIVE_VIEW'
        assert 'ConditionExpression' in kwargs

    def test_returns_404_when_missing(self, patched_delete_dynamodb):
        from delete_live_view import handler

        patched_delete_dynamodb.delete_item.side_effect = ClientError(
            {'Error': {
                'Code': 'ConditionalCheckFailedException', 'Message': 'x',
            }},
            'DeleteItem',
        )

        response = handler(_event(), None)
        assert response['statusCode'] == 404

    def test_missing_scope_rejected(self, patched_delete_dynamodb):
        from delete_live_view import handler

        response = handler(_event(scope='api/executions.read'), None)
        assert response['statusCode'] == 403
        patched_delete_dynamodb.delete_item.assert_not_called()

    def test_bad_path_rejected(self, patched_delete_dynamodb):
        from delete_live_view import handler

        response = handler(_event(execution_id='../bad'), None)
        assert response['statusCode'] == 400

    def test_dynamodb_error_returns_500(self, patched_delete_dynamodb):
        from delete_live_view import handler

        patched_delete_dynamodb.delete_item.side_effect = ClientError(
            {'Error': {'Code': 'ThrottlingException', 'Message': 'x'}},
            'DeleteItem',
        )

        response = handler(_event(), None)
        assert response['statusCode'] == 500
