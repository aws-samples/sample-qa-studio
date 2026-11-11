"""Shared helpers of the presigned artifact-upload Lambdas (artifact_upload.py)."""
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from artifact_upload import (
    UPLOAD_URL_EXPIRES_IN,
    create_artifact_record,
    generate_presigned_upload_url,
    sanitize_filename,
    sanitize_path,
    validate_content_type,
)

_CLIENT_ERROR = ClientError({'Error': {'Code': 'AccessDenied', 'Message': 'no'}}, 'Op')


class TestSanitizeFilename:
    @pytest.mark.parametrize('raw,expected', [
        ('video.webm', 'video.webm'),
        ('../../etc/passwd', '.._.._etc_passwd'),
        ('a\\b.txt', 'a_b.txt'),
        ('nul\0l.txt', 'null.txt'),
        ('', ''),
    ])
    def test_cases(self, raw, expected):
        assert sanitize_filename(raw) == expected

    def test_long_name_keeps_extension(self):
        result = sanitize_filename('a' * 300 + '.webm')
        assert len(result) == 255
        assert result.endswith('.webm')


class TestSanitizePath:
    @pytest.mark.parametrize('raw,expected', [
        ('session-1/act_2.html', 'session-1/act_2.html'),
        ('../../etc/passwd', 'etc/passwd'),
        ('/abs/x.html', 'abs/x.html'),
        ('a\\b\\c.json', 'a/b/c.json'),
        ('a//b/./c', 'a/b/./c'),
        ('x\0y/z', 'xy/z'),
        ('../..', ''),
    ])
    def test_cases(self, raw, expected):
        assert sanitize_path(raw) == expected


class TestValidateContentType:
    def test_allowed_passes(self):
        validate_content_type('video/webm', ['video/webm'], 'nope')

    def test_rejected_raises_given_message(self):
        with pytest.raises(ValueError, match='^nope$'):
            validate_content_type('text/html', ['video/webm'], 'nope')

    def test_empty_allow_list_rejects_everything(self):
        with pytest.raises(ValueError):
            validate_content_type('text/plain', [], 'x')


class TestCreateArtifactRecord:
    def _call(self, dynamodb, **extra):
        create_artifact_record(
            dynamodb, 'table-1',
            artifact_id='a-1', execution_id='e-1', artifact_type='recording',
            filename='v.webm', content_type='video/webm', s3_bucket='b',
            s3_key='u/e-1/v.webm', created_at='2026-01-01T00:00:00Z', **extra,
        )
        return dynamodb.put_item.call_args.kwargs

    def test_record_shape(self):
        kwargs = self._call(MagicMock())
        assert kwargs['TableName'] == 'table-1'
        assert kwargs['Item'] == {
            'pk': {'S': 'EXECUTION#e-1'}, 'sk': {'S': 'ARTIFACT#a-1'},
            'artifact_id': {'S': 'a-1'}, 'execution_id': {'S': 'e-1'},
            'type': {'S': 'recording'}, 'filename': {'S': 'v.webm'},
            'content_type': {'S': 'video/webm'}, 's3_bucket': {'S': 'b'},
            's3_key': {'S': 'u/e-1/v.webm'}, 'upload_status': {'S': 'pending'},
            'created_at': {'S': '2026-01-01T00:00:00Z'},
        }

    def test_step_id_added_for_step_artifacts(self):
        assert self._call(MagicMock(), step_id='s-1')['Item']['step_id'] == {'S': 's-1'}

    def test_dynamodb_error_propagates(self):
        dynamodb = MagicMock()
        dynamodb.put_item.side_effect = _CLIENT_ERROR
        with pytest.raises(ClientError):
            self._call(dynamodb)


class TestGeneratePresignedUploadUrl:
    def test_put_object_url_enforces_content_type(self):
        s3 = MagicMock()
        s3.generate_presigned_url.return_value = 'https://signed'
        url = generate_presigned_upload_url(s3, s3_bucket='b', s3_key='k', content_type='text/plain')
        assert url == 'https://signed'
        s3.generate_presigned_url.assert_called_once_with(
            'put_object',
            Params={'Bucket': 'b', 'Key': 'k', 'ContentType': 'text/plain'},
            ExpiresIn=UPLOAD_URL_EXPIRES_IN,
        )

    def test_s3_error_propagates(self):
        s3 = MagicMock()
        s3.generate_presigned_url.side_effect = _CLIENT_ERROR
        with pytest.raises(ClientError):
            generate_presigned_upload_url(s3, s3_bucket='b', s3_key='k', content_type='x')
