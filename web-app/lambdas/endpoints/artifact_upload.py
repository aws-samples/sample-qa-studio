"""Shared helpers of the presigned artifact-upload Lambdas.

``generate_execution_artifact_url``, ``generate_step_artifact_url`` and
``generate_suite_artifact_url`` each keep only their path validation, existence
checks and S3 key layout; the sanitising, content-type check, ARTIFACT# record
and presigned PUT live here.  AWS clients are passed in, so each handler keeps
its own ``get_*_client`` seam (tests patch those).
"""
import os
from typing import Any, Optional, Sequence

from botocore.exceptions import ClientError

#: Maximum file-name length kept by :func:`sanitize_filename`.
MAX_FILENAME_LENGTH = 255

#: Presigned upload URL lifetime (seconds) used by all three handlers.
UPLOAD_URL_EXPIRES_IN = 3600


def sanitize_filename(filename: str) -> str:
    """Make ``filename`` a single safe key segment.

    Path separators become ``_``, null bytes are dropped, and the name is cut to
    255 characters keeping the extension.
    """
    sanitized = filename.replace('/', '_').replace('\\', '_').replace('\0', '')
    if len(sanitized) > MAX_FILENAME_LENGTH:
        name, ext = os.path.splitext(sanitized)
        sanitized = name[:MAX_FILENAME_LENGTH - len(ext)] + ext
    return sanitized


def sanitize_path(path: str) -> str:
    """Sanitize a relative path while keeping its directory structure.

    Null bytes are dropped, backslashes become ``/``, leading slashes and empty
    or ``..`` components are removed (no traversal out of the key prefix).
    """
    sanitized = path.replace('\0', '').replace('\\', '/').lstrip('/')
    return '/'.join(c for c in sanitized.split('/') if c and c != '..')


def validate_content_type(content_type: str, allowed: Sequence[str], error_message: str) -> None:
    """Raise ``ValueError(error_message)`` unless ``content_type`` is in ``allowed``."""
    if content_type not in allowed:
        raise ValueError(error_message)


def create_artifact_record(
    dynamodb: Any,
    table_name: str,
    *,
    artifact_id: str,
    execution_id: str,
    artifact_type: str,
    filename: str,
    content_type: str,
    s3_bucket: str,
    s3_key: str,
    created_at: str,
    step_id: Optional[str] = None,
) -> None:
    """Put the ``EXECUTION#{execution_id}`` / ``ARTIFACT#{artifact_id}`` record (status ``pending``)."""
    item = {
        'pk': {'S': f'EXECUTION#{execution_id}'},
        'sk': {'S': f'ARTIFACT#{artifact_id}'},
        'artifact_id': {'S': artifact_id},
        'execution_id': {'S': execution_id},
        'type': {'S': artifact_type},
        'filename': {'S': filename},
        'content_type': {'S': content_type},
        's3_bucket': {'S': s3_bucket},
        's3_key': {'S': s3_key},
        'upload_status': {'S': 'pending'},
        'created_at': {'S': created_at},
    }
    if step_id:
        item['step_id'] = {'S': step_id}
    try:
        dynamodb.put_item(TableName=table_name, Item=item)
        print(f'Created artifact record: {artifact_id}')
    except ClientError as e:
        print(f'DynamoDB error creating artifact record: {str(e)}')
        raise


def generate_presigned_upload_url(
    s3_client: Any,
    *,
    s3_bucket: str,
    s3_key: str,
    content_type: str,
    expires_in: int = UPLOAD_URL_EXPIRES_IN,
) -> str:
    """Presigned ``put_object`` URL that enforces ``content_type``."""
    try:
        return s3_client.generate_presigned_url(
            'put_object',
            Params={'Bucket': s3_bucket, 'Key': s3_key, 'ContentType': content_type},
            ExpiresIn=expires_in,
        )
    except ClientError as e:
        print(f'S3 error generating presigned URL: {str(e)}')
        raise
