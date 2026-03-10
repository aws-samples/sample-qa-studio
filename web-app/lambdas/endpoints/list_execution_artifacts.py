"""
AWS Lambda function to list execution-level artifacts from DynamoDB.
Generates presigned download URLs for each confirmed artifact.

Endpoint: GET /usecase/{id}/executions/{executionId}/artifacts
"""
import json
import os
import boto3
from botocore.exceptions import ClientError
from utils import create_response, get_table_name, require_scopes


def get_dynamodb_client():
    """Get DynamoDB client (lazy initialization for testing)."""
    return boto3.client('dynamodb')


def get_s3_client():
    """Get Amazon S3 client (lazy initialization for testing)."""
    return boto3.client('s3')


def generate_presigned_download_url(
    s3_bucket: str,
    s3_key: str,
    expires_in: int = 3600,
) -> str:
    """
    Generate presigned URL for Amazon S3 GetObject operation.

    Args:
        s3_bucket: Amazon S3 bucket name
        s3_key: Amazon S3 object key
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
    List execution-level artifacts by querying DynamoDB.

    Only returns artifacts with upload_status='uploaded'.
    Generates presigned download URLs for each artifact.

    Path Parameters:
    - id: Usecase ID
    - executionId: Execution ID

    Returns:
    - 200: { artifacts: [{ artifact_id, type, filename, content_type, download_url, created_at }] }
    - 400: Missing path parameters
    - 403: Insufficient permissions
    - 500: Internal server error
    """
    # Validate scopes
    user_identity, error_response = require_scopes(event, ['api/executions.read'])
    if error_response:
        return error_response

    print(f"Execution artifact list requested by: {user_identity['identity']} (type: {user_identity['identity_type']})")

    # Parse path parameters
    execution_id = event.get('pathParameters', {}).get('executionId')

    if not execution_id:
        return create_response(400, {
            'error': 'Missing required path parameters',
            'message': 'executionId is required',
        })

    # Query Amazon DynamoDB for artifact records
    dynamodb = get_dynamodb_client()
    table_name = get_table_name()

    try:
        response = dynamodb.query(
            TableName=table_name,
            KeyConditionExpression='pk = :pk AND begins_with(sk, :sk_prefix)',
            ExpressionAttributeValues={
                ':pk': {'S': f'EXECUTION#{execution_id}'},
                ':sk_prefix': {'S': 'ARTIFACT#'},
            },
        )
    except ClientError as e:
        print(f'DynamoDB error querying artifacts: {str(e)}')
        return create_response(500, {
            'error': 'Failed to list artifacts',
            'message': 'Internal server error',
        })

    # Filter for uploaded artifacts and build response
    artifacts = []
    for item in response.get('Items', []):
        upload_status = item.get('upload_status', {}).get('S', '')
        if upload_status != 'uploaded':
            continue

        s3_bucket = item.get('s3_bucket', {}).get('S', '')
        s3_key = item.get('s3_key', {}).get('S', '')

        if not s3_bucket or not s3_key:
            continue

        try:
            download_url = generate_presigned_download_url(
                s3_bucket=s3_bucket,
                s3_key=s3_key,
                expires_in=3600,
            )
        except ClientError as e:
            print(f'S3 error generating download URL for {s3_key}: {str(e)}')
            continue

        artifacts.append({
            'artifact_id': item.get('artifact_id', {}).get('S', ''),
            'type': item.get('type', {}).get('S', ''),
            'filename': item.get('filename', {}).get('S', ''),
            'content_type': item.get('content_type', {}).get('S', ''),
            'download_url': download_url,
            'created_at': item.get('created_at', {}).get('S', ''),
        })

    print(json.dumps({
        'event': 'execution_artifacts_listed',
        'execution_id': execution_id,
        'artifact_count': len(artifacts),
        'user_identity': user_identity['identity'],
    }))

    return create_response(200, {'artifacts': artifacts})
