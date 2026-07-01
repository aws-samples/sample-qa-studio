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
        # The request body field is ``live_view_url`` (public API
        # contract) but the DDB field is ``live_url`` — that's the
        # name both readers (frontend hook, wizard worker) agree on.
        assert item['live_url']['S'] == 'https://live.example/session/abc'
        assert 'live_view_url' not in item, (
            "regression: Lambda must not write ``live_view_url`` to DDB — "
            "readers look for ``live_url``"
        )
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


# ---------------------------------------------------------------------------
# Wire-shape contract — write → DDB → read
# ---------------------------------------------------------------------------
#
# This test class exists specifically because the live-view flow was
# silently broken for every OnDemandHeadless execution: the write path
# stored the URL under a different field name than the read path (and
# the frontend) expected, so the UI showed "no live view" even though
# the record existed. The tests here pin the full wire shape so a
# future field rename on any single side will fail CI instead of
# shipping silently broken.


def _ddb_item_to_plain(item: dict) -> dict:
    """Convert a low-level DDB-typed item (``{'S': 'foo'}``) to the
    plain dict shape that the resource-level ``table.get_item`` API
    returns — so we can feed the write output straight into the read
    mock and exercise the round-trip in one test.
    """
    def _unwrap(value):
        if not isinstance(value, dict) or len(value) != 1:
            return value
        (type_tag, inner), = value.items()
        if type_tag in ('S', 'N'):
            return inner
        return value

    return {key: _unwrap(value) for key, value in item.items()}


class TestLiveViewWireShape:
    def test_write_read_round_trip_exposes_live_url_to_frontend(
        self, monkeypatch, patched_create_dynamodb,
    ):
        """The end-to-end contract the frontend depends on:

        1. CLI POSTs ``{"live_view_url": "https://..."}``.
        2. Lambda writes a DDB item containing ``live_url``.
        3. GET handler returns that item as-is.
        4. Frontend (``useLiveViewUrl``) reads ``response.live_url``.

        If any link in that chain renames the field, the live view
        silently disappears — this test locks the shape end to end.
        """

        # --- 1. Write ------------------------------------------------------
        from create_live_view import handler as create_handler

        patched_create_dynamodb.put_item.return_value = {}

        create_response = create_handler(
            _event({'live_view_url': 'https://live.example/session/xyz'}),
            None,
        )
        assert create_response['statusCode'] == 200

        written_item = patched_create_dynamodb.put_item.call_args.kwargs['Item']
        # --- 2. DDB field presence ----------------------------------------
        assert 'live_url' in written_item, (
            "write-side regression: Lambda must store the URL under "
            "``live_url`` so the frontend can read it"
        )

        # --- 3. Read — mock the resource-level get_item to return the
        # same item shape DDB would produce on read.
        plain_item = _ddb_item_to_plain(written_item)

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': plain_item}
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        # Keep the read handler's ``boto3.resource`` call pointed at
        # our mock without affecting any other tests in the module.
        import boto3
        monkeypatch.setattr(boto3, 'resource', lambda *_args, **_kwargs: mock_resource)

        from get_live_view import handler as get_handler

        get_event = {
            'httpMethod': 'GET',
            'pathParameters': {'id': 'uc-1', 'executionId': 'exec-1'},
            'requestContext': {
                'authorizer': {
                    'client_id': 'test-client',
                    'scope': 'api/executions.read',
                },
            },
        }
        get_response = get_handler(get_event, None)

        assert get_response['statusCode'] == 200
        body = json.loads(get_response['body'])

        # --- 4. Frontend-visible field ------------------------------------
        # ``useLiveViewUrl.ts`` specifically reads ``response.live_url``.
        # Assert the field is present AND equals the URL we POSTed.
        assert body.get('live_url') == 'https://live.example/session/xyz', (
            "read-side regression: GET must return the URL under "
            "``live_url`` — the frontend hook looks for exactly that key"
        )
