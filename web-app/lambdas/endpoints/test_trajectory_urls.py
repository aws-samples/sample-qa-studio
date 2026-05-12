"""Tests for trajectory upload/download URL handlers (R-API-5)."""

import json
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError


def _event(
    body=None,
    usecase_id='uc-1',
    step_id='step-1',
    scope='api/executions.write',
):
    event = {
        'pathParameters': {'id': usecase_id, 'stepId': step_id},
        'requestContext': {
            'authorizer': {'client_id': 'test-client', 'scope': scope},
        },
    }
    if body is not None:
        event['body'] = json.dumps(body)
    return event


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv('TABLE_NAME', 'test-table')
    monkeypatch.setenv('BUCKET_NAME', 'test-bucket')


# ---------------------------------------------------------------------------
# create_trajectory_upload_url
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_upload(monkeypatch):
    s3 = MagicMock()
    s3.generate_presigned_url.return_value = 'https://presigned.example/put'
    ddb = MagicMock()
    monkeypatch.setattr('create_trajectory_upload_url._s3', s3)
    monkeypatch.setattr('create_trajectory_upload_url._dynamodb', ddb)
    return s3, ddb


class TestUploadUrl:
    def test_happy_path(self, patched_upload):
        s3, ddb = patched_upload
        ddb.update_item.return_value = {}

        from create_trajectory_upload_url import handler

        response = handler(_event({'content_type': 'application/json'}), None)
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['upload_url'] == 'https://presigned.example/put'
        assert body['s3_key'] == 'uc-1/trajectories/step-1.json'
        assert body['expires_in'] > 0

        # Step record should have the pointer set.
        ddb.update_item.assert_called_once()
        upd_kwargs = ddb.update_item.call_args.kwargs
        assert upd_kwargs['Key']['pk']['S'] == 'USECASE#uc-1'
        assert upd_kwargs['Key']['sk']['S'] == 'STEP#step-1'
        assert 'trajectory_s3_key' in upd_kwargs['UpdateExpression']
        assert 'trajectory_last_updated' in upd_kwargs['UpdateExpression']

        # Presigned URL was requested for put_object with our key.
        s3.generate_presigned_url.assert_called_once()
        pu_kwargs = s3.generate_presigned_url.call_args.kwargs
        assert pu_kwargs['ClientMethod'] == 'put_object'
        assert pu_kwargs['Params']['Bucket'] == 'test-bucket'
        assert pu_kwargs['Params']['Key'] == 'uc-1/trajectories/step-1.json'
        assert pu_kwargs['Params']['ContentType'] == 'application/json'

    def test_default_content_type(self, patched_upload):
        s3, ddb = patched_upload
        ddb.update_item.return_value = {}

        from create_trajectory_upload_url import handler

        response = handler(_event({}), None)
        assert response['statusCode'] == 200
        # Default to application/json if caller omits it.
        pu_kwargs = s3.generate_presigned_url.call_args.kwargs
        assert pu_kwargs['Params']['ContentType'] == 'application/json'

    def test_missing_body_is_ok(self, patched_upload):
        s3, ddb = patched_upload
        ddb.update_item.return_value = {}

        from create_trajectory_upload_url import handler

        response = handler(_event(body=None), None)
        assert response['statusCode'] == 200

    def test_non_json_body_rejected(self, patched_upload):
        from create_trajectory_upload_url import handler

        event = _event({})
        event['body'] = 'not-json'
        response = handler(event, None)
        assert response['statusCode'] == 400

    def test_invalid_content_type_rejected(self, patched_upload):
        from create_trajectory_upload_url import handler

        response = handler(_event({'content_type': 'text/html'}), None)
        assert response['statusCode'] == 400

    def test_missing_scope_rejected(self, patched_upload):
        from create_trajectory_upload_url import handler

        response = handler(
            _event({'content_type': 'application/json'}, scope='api/executions.read'),
            None,
        )
        assert response['statusCode'] == 403

    def test_bad_step_id_rejected(self, patched_upload):
        from create_trajectory_upload_url import handler

        response = handler(_event({}, step_id='../bad'), None)
        assert response['statusCode'] == 400

    def test_s3_error_returns_500(self, patched_upload):
        s3, _ = patched_upload
        s3.generate_presigned_url.side_effect = ClientError(
            {'Error': {'Code': 'SomeError', 'Message': 'x'}},
            'GeneratePresignedUrl',
        )

        from create_trajectory_upload_url import handler

        response = handler(_event({}), None)
        assert response['statusCode'] == 500


# ---------------------------------------------------------------------------
# get_trajectory_download_url
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_download(monkeypatch):
    s3 = MagicMock()
    s3.generate_presigned_url.return_value = 'https://presigned.example/get'
    ddb = MagicMock()
    monkeypatch.setattr('get_trajectory_download_url._s3', s3)
    monkeypatch.setattr('get_trajectory_download_url._dynamodb', ddb)
    return s3, ddb


class TestDownloadUrl:
    def test_happy_path(self, patched_download):
        s3, ddb = patched_download
        ddb.get_item.return_value = {
            'Item': {
                'pk': {'S': 'USECASE#uc-1'},
                'sk': {'S': 'STEP#step-1'},
                'trajectory_s3_key': {'S': 'uc-1/trajectories/step-1.json'},
            }
        }

        from get_trajectory_download_url import handler

        response = handler(_event(), None)
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['download_url'] == 'https://presigned.example/get'
        assert body['expires_in'] > 0

        pu_kwargs = s3.generate_presigned_url.call_args.kwargs
        assert pu_kwargs['ClientMethod'] == 'get_object'
        assert pu_kwargs['Params']['Key'] == 'uc-1/trajectories/step-1.json'

    def test_no_trajectory_returns_404(self, patched_download):
        s3, ddb = patched_download
        ddb.get_item.return_value = {
            'Item': {
                'pk': {'S': 'USECASE#uc-1'},
                'sk': {'S': 'STEP#step-1'},
            }
        }

        from get_trajectory_download_url import handler

        response = handler(_event(), None)
        assert response['statusCode'] == 404
        s3.generate_presigned_url.assert_not_called()

    def test_missing_step_returns_404(self, patched_download):
        s3, ddb = patched_download
        ddb.get_item.return_value = {}

        from get_trajectory_download_url import handler

        response = handler(_event(), None)
        assert response['statusCode'] == 404

    def test_missing_scope_rejected(self, patched_download):
        from get_trajectory_download_url import handler

        response = handler(_event(scope='api/executions.read'), None)
        assert response['statusCode'] == 403

    def test_bad_step_id_rejected(self, patched_download):
        from get_trajectory_download_url import handler

        response = handler(_event(step_id='../bad'), None)
        assert response['statusCode'] == 400

    def test_dynamodb_error_returns_500(self, patched_download):
        _, ddb = patched_download
        ddb.get_item.side_effect = ClientError(
            {'Error': {'Code': 'x', 'Message': 'x'}}, 'GetItem',
        )

        from get_trajectory_download_url import handler

        response = handler(_event(), None)
        assert response['statusCode'] == 500
