"""Tests for trajectory upload/download URL handlers (R-API-5)."""

import json
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from authz_test_support import (
    UC_ID, make_event, owned_everything, owned_resources, share, worker_header,
)


def _event(
    body=None,
    usecase_id='uc-1',
    step_id='step-1',
    scope='api/executions.write api/executions.read',
    caller='executor_a',
    **kwargs,
):
    return make_event(caller, path={'id': usecase_id, 'stepId': step_id}, body=body,
                      scopes=scope, **kwargs)


@pytest.fixture(autouse=True)
def _owned():
    with owned_everything():
        yield


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

        response = handler(_event(scope='api/executions.write'), None)
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


class TestTrajectoryAccess:
    """Upload needs execute, download needs view on the owning app; worker via capability (H-2)."""

    def _call(self, module, caller, **owned):
        import importlib
        handler = importlib.import_module(module).handler
        extra = {'worker_header': worker_header()} if caller == 'worker' else {}
        with owned_resources(**owned):
            return handler(_event(usecase_id=UC_ID, caller=caller, **extra), None)

    @pytest.mark.parametrize('caller,expected', [
        ('executor_a', 200), ('admin', 200), ('client_a', 200), ('worker', 200),
        ('viewer_a', 403), ('executor_b', 403), ('client_unbound', 403),
    ])
    def test_upload(self, patched_upload, caller, expected):
        patched_upload[1].update_item.return_value = {}
        assert self._call('create_trajectory_upload_url', caller)['statusCode'] == expected

    def test_upload_shared_execute(self, patched_upload):
        patched_upload[1].update_item.return_value = {}
        response = self._call('create_trajectory_upload_url', 'executor_b', shares=share('execute'))
        assert response['statusCode'] == 200

    @pytest.mark.parametrize('caller,expected', [
        ('viewer_a', 404), ('admin', 404), ('worker', 404),  # authorized; no trajectory recorded
        ('viewer_b', 403), ('editor_b', 403), ('client_unbound', 403),
    ])
    def test_download(self, patched_download, caller, expected):
        patched_download[1].get_item.return_value = {}
        assert self._call('get_trajectory_download_url', caller)['statusCode'] == expected

    def test_download_needs_executions_read_not_write(self, patched_download):
        from get_trajectory_download_url import handler
        patched_download[1].get_item.return_value = {}
        response = handler(_event(scope='api/executions.read', caller='viewer_a'), None)
        assert response['statusCode'] == 404

    def test_worker_token_for_other_usecase_denied(self, patched_upload):
        from create_trajectory_upload_url import handler
        event = _event(usecase_id=UC_ID, caller='worker', worker_header=worker_header(usecase_id='uc-other'))
        with owned_resources():
            assert handler(event, None)['statusCode'] == 403
