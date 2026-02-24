"""
Lambda function to generate presigned S3 URLs for suite-level artifacts.
No DynamoDB artifact record is created — artifacts are discovered via S3 ListObjectsV2.
"""
import json
import os
import boto3
from botocore.exceptions import ClientError
from utils import (
    create_response,
    get_table_name,
    require_scopes
)


def get_dynamodb_client():
    """Get DynamoDB client (lazy initialization for testing)"""
    return boto3.client('dynamodb')


def get_s3_client():
    """Get S3 client (lazy initialization for testing)"""
    return boto3.client('s3')


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent security issues.

    - Remove path separators (/, \\)
    - Remove null bytes
    - Limit length to 255 characters
    - Preserve file extension
    """
    sanitized = filename.replace('/', '_').replace('\\', '_').replace('\0', '')

    if len(sanitized) > 255:
        name, ext = os.path.splitext(sanitized)
        sanitized = name[:255-len(ext)] + ext

    return sanitized


def validate_suite_execution_exists(suite_id: str, execution_id: str) -> dict:
    """
    Verify suite execution record exists in DynamoDB.

    Query: pk='SUITE_EXECUTION#{suite_id}', sk='EXECUTION#{execution_id}'

    Returns:
        Suite execution record

    Raises:
        ValueError: If suite execution not found
    """
    dynamodb = get_dynamodb_client()
    table_name = get_table_name()

    try:
        response = dynamodb.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'SUITE_EXECUTION#{suite_id}'},
                'sk': {'S': f'EXECUTION#{execution_id}'}
            }
        )

        if 'Item' not in response:
            raise ValueError(f'Suite execution not found: {execution_id}')

        return response['Item']
    except ClientError as e:
        print(f'DynamoDB error validating suite execution: {str(e)}')
        raise


def generate_s3_key(suite_id: str, suite_execution_id: str, filename: str) -> str:
    """
    Generate S3 key for suite-level artifact.

    Format: suites/{suite_id}/{suite_execution_id}/{filename}
    """
    sanitized_filename = sanitize_filename(filename)
    return f'suites/{suite_id}/{suite_execution_id}/{sanitized_filename}'


def generate_presigned_upload_url(
    s3_bucket: str,
    s3_key: str,
    content_type: str,
    expires_in: int = 3600
) -> str:
    """
    Generate presigned URL for S3 PutObject operation.

    Args:
        s3_bucket: S3 bucket name
        s3_key: S3 object key
        content_type: MIME type (enforced in presigned URL)
        expires_in: Expiration time in seconds (default 1 hour)

    Returns:
        Presigned URL string
    """
    s3_client = get_s3_client()
    try:
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': s3_bucket,
                'Key': s3_key,
                'ContentType': content_type
            },
            ExpiresIn=expires_in
        )
        return presigned_url
    except ClientError as e:
        print(f'S3 error generating presigned URL: {str(e)}')
        raise


def handler(event, context):
    """
    Generate presigned S3 URL for suite-level artifacts.

    No DynamoDB artifact record is created. Artifacts are discovered
    via S3 ListObjectsV2 at read time.

    Path Parameters:
    - suiteId: Suite ID
    - executionId: Suite Execution ID

    Request Body:
    - type: Artifact type (e.g. "logs")
    - filename: Original filename
    - content_type: MIME type

    Returns:
    - 200: { upload_url, expires_in, s3_key }
    - 400: Invalid request (missing fields, invalid type)
    - 403: Insufficient permissions
    - 404: Suite execution not found
    - 500: Internal server error
    """
    # Validate scopes
    user_identity, error_response = require_scopes(event, ['api/suite.write'])
    if error_response:
        return error_response

    print(f"Suite artifact URL requested by: {user_identity['identity']} (type: {user_identity['identity_type']})")

    # Parse path parameters
    suite_id = event.get('pathParameters', {}).get('suite_id')
    execution_id = event.get('pathParameters', {}).get('execution_id')

    if not suite_id or not execution_id:
        return create_response(400, {
            'error': 'Missing required path parameters',
            'message': 'suiteId and executionId are required'
        })

    # Parse request body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return create_response(400, {
            'error': 'Invalid JSON',
            'message': 'Request body must be valid JSON'
        })

    artifact_type = body.get('type')
    filename = body.get('filename')
    content_type = body.get('content_type')

    # Validate required fields
    if not artifact_type or not filename or not content_type:
        return create_response(400, {
            'error': 'Missing required fields',
            'message': 'type, filename, and content_type are required'
        })

    # Validate artifact type
    ALLOWED_SUITE_TYPES = ['logs', 'recording']
    if artifact_type not in ALLOWED_SUITE_TYPES:
        return create_response(400, {
            'error': 'Invalid artifact type',
            'message': f'Artifact type must be one of: {", ".join(ALLOWED_SUITE_TYPES)}'
        })

    # Validate suite execution exists
    try:
        validate_suite_execution_exists(suite_id, execution_id)
    except ValueError:
        return create_response(404, {
            'error': 'Suite execution not found',
            'message': f'No suite execution found with ID: {execution_id}'
        })
    except Exception as e:
        print(f'Error validating suite execution: {str(e)}')
        return create_response(500, {
            'error': 'Failed to validate suite execution',
            'message': 'Internal server error'
        })

    # Generate S3 key
    s3_key = generate_s3_key(suite_id, execution_id, filename)

    # Get S3 bucket name from environment
    s3_bucket = os.environ.get('BUCKET_NAME')
    if not s3_bucket:
        print('ERROR: BUCKET_NAME environment variable not set')
        return create_response(500, {
            'error': 'Configuration error',
            'message': 'Internal server error'
        })

    # Generate presigned URL — no DynamoDB artifact record created
    try:
        presigned_url = generate_presigned_upload_url(
            s3_bucket=s3_bucket,
            s3_key=s3_key,
            content_type=content_type,
            expires_in=3600  # 1 hour
        )
    except Exception as e:
        print(f'Error generating presigned URL: {str(e)}')
        return create_response(500, {
            'error': 'Failed to generate presigned URL',
            'message': 'Internal server error'
        })

    # Log artifact URL generation (never log the presigned URL itself)
    print(json.dumps({
        'event': 'suite_artifact_url_generated',
        'suite_id': suite_id,
        'execution_id': execution_id,
        'artifact_type': artifact_type,
        'filename': filename,
        'user_identity': user_identity['identity']
    }))

    # Return response — no artifact_id since no DynamoDB record
    return create_response(200, {
        'upload_url': presigned_url,
        'expires_in': 3600,
        's3_key': s3_key
    })
