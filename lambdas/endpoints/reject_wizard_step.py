import logging
import json
from typing import Any, Dict
import boto3
from utils import create_response, get_table_name, require_scopes

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to reject a wizard step.
    Marks the step as rejected so the user can retry or skip it.
    """
    # Validate scopes - rejecting wizard steps modifies usecases
    user_identity, error = require_scopes(event, ['api/usecases.write'])
    if error:
        return error

    try:
        path_params = event.get('pathParameters', {})
        session_id = path_params.get('sessionId')
        step_id = path_params.get('stepId')
        usecase_id = path_params.get('usecaseId')

        if not session_id or not step_id or not usecase_id:
            return create_response(400, {'error': 'Missing required parameters'})

        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())

        # Verify the step exists
        response = table.get_item(
            Key={
                'pk': f'EXECUTION#{session_id}',
                'sk': f'EXECUTION_STEP#{step_id}'
            }
        )

        if 'Item' not in response:
            return create_response(404, {'error': 'Step not found'})

        # Update execution step to rejected
        table.update_item(
            Key={
                'pk': f'EXECUTION#{session_id}',
                'sk': f'EXECUTION_STEP#{step_id}'
            },
            UpdateExpression='SET acceptance_status = :status',
            ExpressionAttributeValues={
                ':status': 'rejected'
            }
        )

        logger.info(f"Rejected wizard step {step_id} for session {session_id}")

        return create_response(200, {
            'status': 'rejected',
            'step_id': step_id
        })

    except Exception as e:
        logger.error(f"Error rejecting wizard step: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
