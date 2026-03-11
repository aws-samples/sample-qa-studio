"""
AWS Lambda function to confirm artifact upload completion.

After uploading a file to S3 via presigned URL, the CI/CD runner calls this
endpoint to update the artifact record's upload_status from 'pending' to 'uploaded'.

Endpoint: PATCH /api/usecase/{id}/executions/{executionId}/artifacts/{artifactId}
"""
import json
import boto3
from utils import (
    create_response,
    get_table_name,
    get_current_timestamp,
    require_scopes,
    validate_path_id)

dynamodb = boto3.client('dynamodb')


def handler(event, context):
    """
    Confirm artifact upload completion.

    Path Parameters:
    - id: Usecase ID
    - executionId: Execution ID
    - artifactId: Artifact ID

    Returns:
    - 200: Upload confirmed
    - 403: Insufficient permissions
    - 404: Artifact not found
    - 500: Internal server error
    """
    # Validate scopes
    user_identity, error_response = require_scopes(event, ['api/executions.write'])
    if error_response:
        return error_response

    # Parse path parameters
    execution_id, error = validate_path_id(event.get('pathParameters', {}).get('executionId'), 'execution ID')
    if error:
        return error

    artifact_id, error = validate_path_id(event.get('pathParameters', {}).get('artifactId'), 'artifact ID')
    if error:
        return error

    table_name = get_table_name()

    try:
        # Verify artifact exists
        response = dynamodb.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'EXECUTION#{execution_id}'},
                'sk': {'S': f'ARTIFACT#{artifact_id}'}
            }
        )

        if 'Item' not in response:
            return create_response(404, {'error': 'Artifact not found'})

        # Update upload_status to uploaded
        dynamodb.update_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'EXECUTION#{execution_id}'},
                'sk': {'S': f'ARTIFACT#{artifact_id}'}
            },
            UpdateExpression='SET upload_status = :status, uploaded_at = :uploaded_at',
            ExpressionAttributeValues={
                ':status': {'S': 'uploaded'},
                ':uploaded_at': {'S': get_current_timestamp()}
            }
        )

        return create_response(200, {
            'artifact_id': artifact_id,
            'upload_status': 'uploaded'
        })

    except Exception as e:
        print(f'Error confirming artifact upload: {str(e)}')
        return create_response(500, {'error': 'Failed to confirm artifact upload'})
