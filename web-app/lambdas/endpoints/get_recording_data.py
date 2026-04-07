import lambda_init  # noqa: F401 — must be first import (adds dependencies/ to sys.path)

import json
import logging
import os

import boto3

from recording_models import RecordingDataResponse, RecordingData
from utils import create_response, get_table_name, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    """
    Return recording data for a wizard session.

    The worker stores recording_status and recording_s3_key on the execution
    record (PK=USECASE_EXECUTION#{usecaseId}, SK=EXECUTION#{sessionId}).
    When status is 'completed', the actual recording data is fetched from S3
    using the stored key.

    Path Parameters:
        sessionId: The wizard session ID

    Query Parameters:
        usecaseId: The usecase ID associated with the session

    Returns:
        200: { "status": "available", "recording_data": <RecordingData> }
             or { "status": "not_available", "recording_data": null }
        400: Missing or invalid sessionId / usecaseId
        403: Insufficient scopes
        404: Execution record not found
        500: Internal error
    """
    # Validate scopes — recording is part of the usecase write workflow
    user_identity, error = require_scopes(event, ['api/usecases.write'])
    if error:
        return error

    # Parse and validate sessionId from path parameters
    session_id, error = validate_path_id(
        event.get('pathParameters', {}).get('sessionId'), 'session ID'
    )
    if error:
        return error

    # Parse and validate usecaseId from query parameters
    usecase_id, error = validate_path_id(
        event.get('queryStringParameters', {}).get('usecaseId') if event.get('queryStringParameters') else None,
        'usecase ID'
    )
    if error:
        return error

    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())

        response = table.get_item(
            Key={
                'pk': f'USECASE_EXECUTION#{usecase_id}',
                'sk': f'EXECUTION#{session_id}'
            },
            ProjectionExpression='recording_status, recording_s3_key, recording_error'
        )

        if 'Item' not in response:
            return create_response(404, {'error': 'Execution record not found'})

        item = response['Item']
        recording_status = item.get('recording_status')
        recording_s3_key = item.get('recording_s3_key')
        recording_error = item.get('recording_error')

        if recording_status == 'error':
            result = RecordingDataResponse(
                status='error',
                error=recording_error or 'Recording failed on the worker'
            )
        elif recording_status == 'completed' and recording_s3_key:
            try:
                s3_client = boto3.client('s3')
                bucket_name = os.environ['BUCKET_NAME']
                s3_response = s3_client.get_object(Bucket=bucket_name, Key=recording_s3_key)
                recording_data_raw = s3_response['Body'].read().decode('utf-8')
                recording_data_dict = json.loads(recording_data_raw)
                recording_data = RecordingData(**recording_data_dict)
                result = RecordingDataResponse(
                    status='available',
                    recording_data=recording_data
                )
            except Exception as e:
                logger.warning(f"Failed to fetch recording data from S3 for session {session_id}: {e}")
                result = RecordingDataResponse(status='not_available')
        else:
            result = RecordingDataResponse(status='not_available')

        return create_response(200, result.model_dump())

    except Exception as e:
        logger.error(f"Error retrieving recording data for session {session_id}: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Failed to retrieve recording data'})
