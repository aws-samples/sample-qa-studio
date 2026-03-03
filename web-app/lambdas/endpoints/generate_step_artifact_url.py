"""
Lambda function to generate presigned S3 URLs for step-level artifacts.
Supports screenshot and trace artifacts.
"""
import json
import os
import boto3
from botocore.exceptions import ClientError
from utils import (
    create_response,
    get_table_name,
    get_current_timestamp,
    generate_uuid7,
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
    # Remove path separators and null bytes
    sanitized = filename.replace('/', '_').replace('\\', '_').replace('\0', '')
    
    # Limit length
    if len(sanitized) > 255:
        name, ext = os.path.splitext(sanitized)
        sanitized = name[:255-len(ext)] + ext
    
    return sanitized


def validate_content_type(content_type: str) -> None:
    """Validate content type is allowed for step artifacts."""
    ALLOWED_CONTENT_TYPES = ['image/png', 'image/jpeg', 'application/json', 'text/html']
    
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError(f'Content type must be one of: {", ".join(ALLOWED_CONTENT_TYPES)}')


def validate_execution_exists(usecase_id: str, execution_id: str) -> dict:
    """
    Verify execution record exists in DynamoDB.
    
    Query: pk='USECASE_EXECUTION#{usecase_id}', sk='EXECUTION#{execution_id}'
    
    Returns:
        Execution record
    
    Raises:
        ValueError: If execution not found
    """
    dynamodb = get_dynamodb_client()
    table_name = get_table_name()
    
    try:
        response = dynamodb.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
                'sk': {'S': f'EXECUTION#{execution_id}'}
            }
        )
        
        if 'Item' not in response:
            raise ValueError(f'Execution not found: {execution_id}')
        
        return response['Item']
    except ClientError as e:
        print(f'DynamoDB error validating execution: {str(e)}')
        raise


def validate_step_exists(execution_id: str, step_id: str) -> dict:
    """
    Verify execution step record exists in DynamoDB.
    
    Query: pk='EXECUTION#{execution_id}', sk='EXECUTION_STEP#{step_id}'
    
    Returns:
        Execution step record
    
    Raises:
        ValueError: If step not found
    """
    dynamodb = get_dynamodb_client()
    table_name = get_table_name()
    
    try:
        response = dynamodb.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'EXECUTION#{execution_id}'},
                'sk': {'S': f'EXECUTION_STEP#{step_id}'}
            }
        )
        
        if 'Item' not in response:
            raise ValueError(f'Step not found: {step_id}')
        
        return response['Item']
    except ClientError as e:
        print(f'DynamoDB error validating step: {str(e)}')
        raise


def generate_s3_key_for_step_artifact(
    usecase_id: str,
    execution_id: str,
    step_id: str,
    filename: str
) -> str:
    """
    Generate S3 key for step-level artifact.
    
    Format: {usecase_id}/{execution_id}/steps/{step_id}/{filename}
    """
    sanitized_filename = sanitize_filename(filename)
    return f'{usecase_id}/{execution_id}/steps/{step_id}/{sanitized_filename}'


def create_artifact_record(
    artifact_id: str,
    execution_id: str,
    artifact_type: str,
    filename: str,
    content_type: str,
    s3_bucket: str,
    s3_key: str,
    created_at: str,
    step_id: str = None
) -> None:
    """
    Create artifact metadata record in DynamoDB.
    
    Put: pk='EXECUTION#{execution_id}', sk='ARTIFACT#{artifact_id}'
    """
    dynamodb = get_dynamodb_client()
    table_name = get_table_name()
    
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
        'created_at': {'S': created_at}
    }
    
    # Add step_id for step-level artifacts
    if step_id:
        item['step_id'] = {'S': step_id}
    
    try:
        dynamodb.put_item(
            TableName=table_name,
            Item=item
        )
        print(f'Created artifact record: {artifact_id}')
    except ClientError as e:
        print(f'DynamoDB error creating artifact record: {str(e)}')
        raise


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
    Generate presigned S3 URL for step-level artifacts (screenshot, trace).
    
    Path Parameters:
    - id: Usecase ID
    - executionId: Execution ID
    - stepId: Step ID
    
    Request Body:
    - filename: Original filename
    - content_type: MIME type
    
    Returns:
    - 200: Presigned URL generated successfully
    - 400: Invalid request (missing fields)
    - 403: Insufficient permissions
    - 404: Execution or step not found
    - 500: Internal server error
    """
    # Validate scopes
    user_identity, error_response = require_scopes(event, ['api/executions.write'])
    if error_response:
        return error_response
    
    print(f"Step artifact URL requested by: {user_identity['identity']} (type: {user_identity['identity_type']})")
    
    # Parse path parameters
    usecase_id = event.get('pathParameters', {}).get('id')
    execution_id = event.get('pathParameters', {}).get('executionId')
    step_id = event.get('pathParameters', {}).get('stepId')
    
    if not usecase_id or not execution_id or not step_id:
        return create_response(400, {
            'error': 'Missing required path parameters',
            'message': 'usecase_id, execution_id, and step_id are required'
        })
    
    # Parse request body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return create_response(400, {
            'error': 'Invalid JSON',
            'message': 'Request body must be valid JSON'
        })
    
    filename = body.get('filename')
    content_type = body.get('content_type')
    
    # Validate required fields
    if not filename or not content_type:
        return create_response(400, {
            'error': 'Missing required fields',
            'message': 'filename and content_type are required'
        })
    
    # Validate content type
    try:
        validate_content_type(content_type)
    except ValueError as e:
        return create_response(400, {
            'error': 'Invalid content type',
            'message': str(e)
        })
    
    # Validate execution exists
    try:
        validate_execution_exists(usecase_id, execution_id)
    except ValueError:
        return create_response(404, {
            'error': 'Execution not found',
            'message': f'No execution found with ID: {execution_id}'
        })
    except Exception as e:
        print(f'Error validating execution: {str(e)}')
        return create_response(500, {
            'error': 'Failed to validate execution',
            'message': 'Internal server error'
        })
    
    # Validate step exists
    try:
        validate_step_exists(execution_id, step_id)
    except ValueError:
        return create_response(404, {
            'error': 'Step not found',
            'message': f'No step found with ID: {step_id}'
        })
    except Exception as e:
        print(f'Error validating step: {str(e)}')
        return create_response(500, {
            'error': 'Failed to validate step',
            'message': 'Internal server error'
        })
    
    # Determine artifact type from content type
    if content_type in ['image/png', 'image/jpeg']:
        artifact_type = 'screenshot'
    elif content_type == 'application/json':
        artifact_type = 'trace'
    elif content_type == 'text/html':
        artifact_type = 'trace'
    else:
        artifact_type = 'unknown'
    
    # Generate artifact ID (UUIDv7 for time-ordered sorting)
    artifact_id = generate_uuid7()
    
    # Generate S3 key
    s3_key = generate_s3_key_for_step_artifact(usecase_id, execution_id, step_id, filename)
    
    # Get S3 bucket name from environment
    s3_bucket = os.environ.get('BUCKET_NAME')
    if not s3_bucket:
        print('ERROR: BUCKET_NAME environment variable not set')
        return create_response(500, {
            'error': 'Configuration error',
            'message': 'Internal server error'
        })
    
    # Create artifact record in DynamoDB
    created_at = get_current_timestamp()
    try:
        create_artifact_record(
            artifact_id=artifact_id,
            execution_id=execution_id,
            artifact_type=artifact_type,
            filename=filename,
            content_type=content_type,
            s3_bucket=s3_bucket,
            s3_key=s3_key,
            created_at=created_at,
            step_id=step_id
        )
    except Exception as e:
        print(f'Error creating artifact record: {str(e)}')
        return create_response(500, {
            'error': 'Failed to create artifact record',
            'message': 'Internal server error'
        })
    
    # Generate presigned URL
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
        'event': 'step_artifact_url_generated',
        'artifact_id': artifact_id,
        'execution_id': execution_id,
        'step_id': step_id,
        'artifact_type': artifact_type,
        'filename': filename,
        'user_identity': user_identity['identity'],
        'timestamp': created_at
    }))
    
    # Return response
    return create_response(200, {
        'artifact_id': artifact_id,
        'upload_url': presigned_url,
        'expires_in': 3600,
        's3_key': s3_key
    })
