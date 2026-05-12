"""Tests for update_mobile_metadata Lambda handler.

Validates R-API-3.
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
            'authorizer': {'client_id': 'test-client', 'scope': scope},
        },
    }
    if body is not None:
        event['body'] = json.dumps(body)
    return event


@pytest.fixture(autouse=True)
def _table_name(monkeypatch):
    monkeypatch.setenv('TABLE_NAME', 'test-table')


@pytest.fixture
def patched_dynamodb(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr('update_mobile_metadata._dynamodb', mock_client)
    return mock_client


class TestHappyPath:
    def test_updates_arn_only(self, patched_dynamodb):
        from update_mobile_metadata import handler

        arn = 'arn:aws:devicefarm:us-west-2:123:session:abc'
        patched_dynamodb.update_item.return_value = {}

        response = handler(
            _event({'device_farm_session_arn': arn}), None,
        )

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['updated_fields'] == ['device_farm_session_arn']
        kwargs = patched_dynamodb.update_item.call_args.kwargs
        assert kwargs['Key']['pk']['S'] == 'USECASE_EXECUTION#uc-1'
        assert kwargs['Key']['sk']['S'] == 'EXECUTION#exec-1'
        assert 'device_farm_session_arn = :v0' in kwargs['UpdateExpression']
        assert kwargs['ExpressionAttributeValues'][':v0']['S'] == arn
        assert kwargs['ConditionExpression'] == 'attribute_exists(pk)'

    def test_updates_multiple_fields(self, patched_dynamodb):
        from update_mobile_metadata import handler

        patched_dynamodb.update_item.return_value = {}

        response = handler(
            _event({
                'device_farm_session_arn': 'arn:aws:devicefarm:us-west-2:1:s:a',
                'device_name': 'Pixel 6',
                'device_os_version': 'Android 13',
            }),
            None,
        )

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['updated_fields'] == [
            'device_farm_session_arn', 'device_name', 'device_os_version',
        ]
        update_expr = patched_dynamodb.update_item.call_args.kwargs['UpdateExpression']
        assert 'device_farm_session_arn = :v0' in update_expr
        assert 'device_name = :v1' in update_expr
        assert 'device_os_version = :v2' in update_expr


class TestValidation:
    def test_missing_scope_rejected(self, patched_dynamodb):
        from update_mobile_metadata import handler

        response = handler(
            _event({'device_name': 'x'}, scope='api/executions.read'),
            None,
        )
        assert response['statusCode'] == 403
        patched_dynamodb.update_item.assert_not_called()

    def test_missing_body_rejected(self, patched_dynamodb):
        from update_mobile_metadata import handler

        response = handler(_event(body=None), None)
        assert response['statusCode'] == 400

    def test_malformed_json_rejected(self, patched_dynamodb):
        from update_mobile_metadata import handler

        event = _event({'device_name': 'x'})
        event['body'] = 'not-json'
        response = handler(event, None)
        assert response['statusCode'] == 400

    def test_non_object_body_rejected(self, patched_dynamodb):
        from update_mobile_metadata import handler

        event = _event({})
        event['body'] = json.dumps(['not', 'object'])
        response = handler(event, None)
        assert response['statusCode'] == 400

    def test_empty_object_rejected(self, patched_dynamodb):
        from update_mobile_metadata import handler

        response = handler(_event({}), None)
        assert response['statusCode'] == 400

    def test_unknown_field_rejected(self, patched_dynamodb):
        from update_mobile_metadata import handler

        response = handler(
            _event({'device_name': 'x', 'status': 'hijack'}), None,
        )
        assert response['statusCode'] == 400
        assert 'status' in json.loads(response['body'])['error']

    def test_invalid_arn_rejected(self, patched_dynamodb):
        from update_mobile_metadata import handler

        response = handler(
            _event({'device_farm_session_arn': 'not-an-arn'}), None,
        )
        assert response['statusCode'] == 400

    def test_non_string_value_rejected(self, patched_dynamodb):
        from update_mobile_metadata import handler

        response = handler(_event({'device_name': 123}), None)
        assert response['statusCode'] == 400

    def test_oversized_value_rejected(self, patched_dynamodb):
        from update_mobile_metadata import handler

        response = handler(_event({'device_name': 'x' * 600}), None)
        assert response['statusCode'] == 400

    def test_bad_path_rejected(self, patched_dynamodb):
        from update_mobile_metadata import handler

        response = handler(
            _event({'device_name': 'x'}, execution_id='../bad'), None,
        )
        assert response['statusCode'] == 400

    def test_none_field_ignored(self, patched_dynamodb):
        from update_mobile_metadata import handler

        patched_dynamodb.update_item.return_value = {}
        # device_name None should be skipped; device_os_version set.
        response = handler(
            _event({
                'device_name': None,
                'device_os_version': 'Android 14',
            }),
            None,
        )
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['updated_fields'] == ['device_os_version']


class TestNotFoundAndError:
    def test_execution_not_found_returns_404(self, patched_dynamodb):
        from update_mobile_metadata import handler

        patched_dynamodb.update_item.side_effect = ClientError(
            {'Error': {
                'Code': 'ConditionalCheckFailedException', 'Message': 'x',
            }},
            'UpdateItem',
        )

        response = handler(_event({'device_name': 'x'}), None)
        assert response['statusCode'] == 404

    def test_generic_error_returns_500(self, patched_dynamodb):
        from update_mobile_metadata import handler

        patched_dynamodb.update_item.side_effect = ClientError(
            {'Error': {'Code': 'ThrottlingException', 'Message': 'x'}},
            'UpdateItem',
        )

        response = handler(_event({'device_name': 'x'}), None)
        assert response['statusCode'] == 500
