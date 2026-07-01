"""Tests for create_runtime_variable Lambda handler.

Validates requirement R-API-1 in
``.kiro/specs/cli-unified-runner/requirements.md``.
"""
import json
from unittest.mock import MagicMock, patch

import pytest


def _event(body=None, usecase_id='uc-1', execution_id='exec-1',
           scope='api/executions.write'):
    return {
        'pathParameters': {'id': usecase_id, 'executionId': execution_id},
        'body': json.dumps(body) if body is not None else '',
        'requestContext': {
            'authorizer': {
                'client_id': 'test-client',
                'scope': scope,
            },
        },
    }


@pytest.fixture
def patched_dynamodb(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr('create_runtime_variable._dynamodb', mock_client)
    return mock_client


@pytest.fixture(autouse=True)
def _table_name(monkeypatch):
    monkeypatch.setenv('TABLE_NAME', 'test-table')


class TestHappyPath:
    def test_upserts_variable(self, patched_dynamodb):
        from create_runtime_variable import handler

        patched_dynamodb.get_item.return_value = {'Item': {'pk': {'S': 'x'}}}
        patched_dynamodb.update_item.return_value = {}

        response = handler(
            _event({'key': 'orderId', 'value': 'ORD-1'}), None,
        )

        assert response['statusCode'] == 200
        assert json.loads(response['body']) == {'status': 'ok', 'key': 'orderId'}
        patched_dynamodb.update_item.assert_called_once()
        kwargs = patched_dynamodb.update_item.call_args.kwargs
        assert kwargs['Key']['pk']['S'] == 'EXECUTION#exec-1'
        assert kwargs['Key']['sk']['S'] == 'EXECUTION_VARIABLES'
        assert kwargs['ExpressionAttributeNames']['#k'] == 'orderId'
        assert kwargs['ExpressionAttributeValues'][':v']['S'] == 'ORD-1'

    def test_coerces_non_string_value(self, patched_dynamodb):
        from create_runtime_variable import handler

        patched_dynamodb.get_item.return_value = {'Item': {}}
        patched_dynamodb.update_item.return_value = {}

        response = handler(_event({'key': 'count', 'value': 42}), None)

        assert response['statusCode'] == 200
        kwargs = patched_dynamodb.update_item.call_args.kwargs
        assert kwargs['ExpressionAttributeValues'][':v']['S'] == '42'

    def test_key_with_reserved_word_uses_alias(self, patched_dynamodb):
        """The handler aliases the variable name so DynamoDB reserved
        words like 'name' or 'status' work. (See 07_learning.md.)"""
        from create_runtime_variable import handler

        patched_dynamodb.get_item.return_value = {'Item': {}}
        patched_dynamodb.update_item.return_value = {}

        response = handler(_event({'key': 'status', 'value': 'ok'}), None)

        assert response['statusCode'] == 200


class TestValidation:
    def test_missing_body_rejected(self, patched_dynamodb):
        from create_runtime_variable import handler

        response = handler(_event(body=None), None)
        assert response['statusCode'] == 400
        patched_dynamodb.update_item.assert_not_called()

    def test_malformed_json_rejected(self, patched_dynamodb):
        from create_runtime_variable import handler

        event = _event({'key': 'k', 'value': 'v'})
        event['body'] = 'not-json'
        response = handler(event, None)
        assert response['statusCode'] == 400

    def test_missing_key_rejected(self, patched_dynamodb):
        from create_runtime_variable import handler

        response = handler(_event({'value': 'v'}), None)
        assert response['statusCode'] == 400

    def test_empty_key_rejected(self, patched_dynamodb):
        from create_runtime_variable import handler

        response = handler(_event({'key': '', 'value': 'v'}), None)
        assert response['statusCode'] == 400

    def test_non_string_key_rejected(self, patched_dynamodb):
        from create_runtime_variable import handler

        response = handler(_event({'key': 123, 'value': 'v'}), None)
        assert response['statusCode'] == 400

    def test_missing_value_rejected(self, patched_dynamodb):
        from create_runtime_variable import handler

        response = handler(_event({'key': 'k'}), None)
        assert response['statusCode'] == 400

    def test_oversized_key_rejected(self, patched_dynamodb):
        from create_runtime_variable import handler

        response = handler(
            _event({'key': 'x' * 200, 'value': 'v'}), None,
        )
        assert response['statusCode'] == 400

    def test_oversized_value_rejected(self, patched_dynamodb):
        from create_runtime_variable import handler

        response = handler(
            _event({'key': 'k', 'value': 'x' * 10000}), None,
        )
        assert response['statusCode'] == 400

    def test_non_object_body_rejected(self, patched_dynamodb):
        from create_runtime_variable import handler

        event = _event({'key': 'k', 'value': 'v'})
        event['body'] = json.dumps(["not", "an", "object"])
        response = handler(event, None)
        assert response['statusCode'] == 400

    def test_bad_usecase_id_rejected(self, patched_dynamodb):
        from create_runtime_variable import handler

        response = handler(
            _event({'key': 'k', 'value': 'v'}, usecase_id='../../evil'),
            None,
        )
        assert response['statusCode'] == 400

    def test_bad_execution_id_rejected(self, patched_dynamodb):
        from create_runtime_variable import handler

        response = handler(
            _event({'key': 'k', 'value': 'v'}, execution_id='nope/traversal'),
            None,
        )
        assert response['statusCode'] == 400


class TestAuth:
    def test_missing_scope_rejected(self, patched_dynamodb):
        from create_runtime_variable import handler

        response = handler(
            _event({'key': 'k', 'value': 'v'}, scope='api/executions.read'),
            None,
        )
        assert response['statusCode'] == 403
        patched_dynamodb.update_item.assert_not_called()


class TestNotFound:
    def test_missing_execution_variables_record_returns_404(self, patched_dynamodb):
        from create_runtime_variable import handler

        patched_dynamodb.get_item.return_value = {}  # no Item

        response = handler(_event({'key': 'k', 'value': 'v'}), None)
        assert response['statusCode'] == 404
        patched_dynamodb.update_item.assert_not_called()


class TestDynamoDBError:
    def test_generic_client_error_returns_500(self, patched_dynamodb):
        from botocore.exceptions import ClientError
        from create_runtime_variable import handler

        patched_dynamodb.get_item.return_value = {'Item': {}}
        patched_dynamodb.update_item.side_effect = ClientError(
            {'Error': {'Code': 'ThrottlingException', 'Message': 'x'}},
            'UpdateItem',
        )

        response = handler(_event({'key': 'k', 'value': 'v'}), None)
        assert response['statusCode'] == 500

    def test_validation_exception_retries_with_map_init(self, patched_dynamodb):
        """When the runtime_variables attribute is missing, the handler
        initializes it with ``if_not_exists`` and retries."""
        from botocore.exceptions import ClientError
        from create_runtime_variable import handler

        patched_dynamodb.get_item.return_value = {'Item': {}}
        patched_dynamodb.update_item.side_effect = [
            ClientError(
                {'Error': {'Code': 'ValidationException', 'Message': 'x'}},
                'UpdateItem',
            ),
            {},
        ]

        response = handler(_event({'key': 'k', 'value': 'v'}), None)
        assert response['statusCode'] == 200
        assert patched_dynamodb.update_item.call_count == 2
        retry_kwargs = patched_dynamodb.update_item.call_args_list[1].kwargs
        assert 'if_not_exists' in retry_kwargs['UpdateExpression']
