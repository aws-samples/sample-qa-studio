"""
Lambda function to list suite-level artifacts by querying S3 directly.
Generates presigned download URLs for each discovered object.
"""
import json
import os
import boto3
from botocore.exceptions import ClientError
from utils import create_response, require_scopes


# Filename extension → (type, content_type) mapping
EXTENSION_TYPE_MAP = {
    '.txt': ('logs', 'text/plain'),
    '.webm': ('recording', 'video/webm'),
    '.mp4': ('recording', 'video/mp4'),
}

DEFAULT_TYPE = 'unknown'
DEFAULT_CONTENT_TYPE = 'application/octet-stream'


def get_s3_client():
    """Get S3 client (lazy initialization for testing)."""
    return boto3.client('s3')


def infer_type_and_content_type(filename: str) -> tuple[str, str]:
    """
    Infer artifact type and content type from filename extension.

    Returns:
        Tuple of (type, content_type)
    """
    for ext, (artifact_type, content_type) in EXTENSION_TYPE_MAP.items():
        if filename.endswith(ext):
            return artifact_type, content_type
    return DEFAULT_TYPE, DEFAULT_CONTENT_TYPE


def generate_presigned_download_url(
    s3_bucket: str,
    s3_key: str,
    expires_in: int = 3600,
) -> str:
    """
    Generate presigned URL for S3 GetObject operation.

    Args:
        s3_bucket: S3 bucket name
        s3_key: S3 object key
        expires_in: Expiration time in seconds (default 1 hour)

    Returns:
        Presigned URL string
    """
    s3_client = get_s3_client()
    return s3_client.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': s3_bucket,
            'Key': s3_key,
        },
        ExpiresIn=expires_in,
    )


def handler(event, context):
    """
    List suite-level artifacts by querying S3 with ListObjectsV2.

    Path Parameters:
    - suiteId: Suite ID
    - executionId: Suite Execution ID

    Returns:
    - 200: { artifacts: [{ filename, type, content_type, download_url, size, last_modified }] }
    - 403: Insufficient permissions
    - 500: Internal server error
    """
    # Validate scopes
    user_identity, error_response = require_scopes(event, ['api/suite.read'])
    if error_response:
        return error_response

    print(f"Suite artifact list requested by: {user_identity['identity']} (type: {user_identity['identity_type']})")

    # Parse path parameters
    suite_id = event.get('pathParameters', {}).get('suite_id')
    execution_id = event.get('pathParameters', {}).get('execution_id')

    if not suite_id or not execution_id:
        return create_response(400, {
            'error': 'Missing required path parameters',
            'message': 'suiteId and executionId are required',
        })

    # Get S3 bucket name from environment
    s3_bucket = os.environ.get('BUCKET_NAME')
    if not s3_bucket:
        print('ERROR: BUCKET_NAME environment variable not set')
        return create_response(500, {
            'error': 'Configuration error',
            'message': 'Internal server error',
        })

    # List objects under the suite execution prefix
    prefix = f'suites/{suite_id}/{execution_id}/'
    s3_client = get_s3_client()

    try:
        response = s3_client.list_objects_v2(
            Bucket=s3_bucket,
            Prefix=prefix,
        )
    except ClientError as e:
        print(f'S3 error listing objects: {str(e)}')
        return create_response(500, {
            'error': 'Failed to list artifacts',
            'message': 'Internal server error',
        })

    # Build artifact list from S3 objects
    artifacts = []
    for obj in response.get('Contents', []):
        s3_key = obj['Key']
        filename = s3_key.split('/')[-1]

        if not filename:
            continue

        artifact_type, content_type = infer_type_and_content_type(filename)

        try:
            download_url = generate_presigned_download_url(
                s3_bucket=s3_bucket,
                s3_key=s3_key,
                expires_in=3600,
            )
        except ClientError as e:
            print(f'S3 error generating download URL for {s3_key}: {str(e)}')
            return create_response(500, {
                'error': 'Failed to generate download URL',
                'message': 'Internal server error',
            })

        artifacts.append({
            'filename': filename,
            'type': artifact_type,
            'content_type': content_type,
            'download_url': download_url,
            'size': obj.get('Size', 0),
            'last_modified': obj['LastModified'].isoformat() if hasattr(obj.get('LastModified', ''), 'isoformat') else str(obj.get('LastModified', '')),
        })

    # Log the list operation
    print(json.dumps({
        'event': 'suite_artifacts_listed',
        'suite_id': suite_id,
        'execution_id': execution_id,
        'artifact_count': len(artifacts),
        'user_identity': user_identity['identity'],
    }))

    return create_response(200, {'artifacts': artifacts})
