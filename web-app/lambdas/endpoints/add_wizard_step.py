import logging
import json
import os
from typing import Any, Dict
from uuid import uuid4
import boto3
from utils import create_response, get_table_name, get_current_timestamp, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to add a step to a wizard session.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with step creation result
    """
    # Validate scopes - adding wizard steps modifies usecases
    user_identity, error = require_scopes(event, ['api/usecases.write'])
    if error:
        return error
    
    try:
        # Get session ID from path
        path_params = event.get('pathParameters', {})
        session_id, error = validate_path_id(event.get('pathParameters', {}).get('sessionId'), 'session ID')
        if error:
            return error
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid JSON in request body'})
        
        # Initialize Amazon DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        sqs_client = boto3.client('sqs')
        eventbridge_client = boto3.client('events')
        
        # Generate step ID
        step_id = str(uuid4())
        now = get_current_timestamp()
        
        # Create temporary execution step
        execution_step = {
            'pk': f'EXECUTION#{session_id}',
            'sk': f'EXECUTION_STEP#{step_id}',
            'step_id': step_id,
            'sort': 0,  # Updated when accepted
            'instruction': body.get('instruction', ''),
            'step_type': body.get('step_type', ''),
            'created_at': now,
            'acceptance_status': 'pending_acceptance',
            'temporary': True
        }
        
        # Add optional fields
        optional_fields = [
            'secret_key', 'validation_type', 'validation_operator',
            'validation_value', 'capture_variable', 'assertion_variable', 'value_type',
            'enable_advanced_click_types', 'value_source',
            'browser_action', 'browser_args',
            'transform_operation', 'transform_args',
        ]
        for field in optional_fields:
            if field in body:
                execution_step[field] = body[field]
        
        # Save step to DynamoDB
        table.put_item(Item=execution_step)
        
        # Send command to Amazon EventBridge or Amazon SQS
        command = {
            'action': 'execute_step',
            'sessionId': session_id,
            'stepId': step_id
        }
        
        event_bus_name = os.environ.get('WIZARD_EVENT_BUS_NAME', '')
        
        if event_bus_name:
            # Send to Amazon EventBridge (new approach)
            try:
                eventbridge_client.put_events(
                    Entries=[
                        {
                            'Source': 'wizard.commands',
                            'DetailType': 'WizardCommand',
                            'Detail': json.dumps(command),
                            'EventBusName': event_bus_name
                        }
                    ]
                )
                logger.info(f"Command sent to Amazon EventBridge for session {session_id}")
            except Exception as e:
                logger.error(f"Error sending Amazon EventBridge event: {str(e)}")
                return create_response(500, {'error': 'Failed to send command to EventBridge'})
        else:
            # Fallback to Amazon SQS (legacy approach)
            queue_url = os.environ.get('WIZARD_QUEUE_URL', '')
            if queue_url:
                try:
                    sqs_client.send_message(
                        QueueUrl=queue_url,
                        MessageBody=json.dumps(command)
                    )
                    logger.info(f"Command sent to SQS for session {session_id}")
                except Exception as e:
                    logger.error(f"Error sending SQS message: {str(e)}")
                    return create_response(500, {'error': 'Failed to send command to SQS'})
        
        return create_response(201, {
            'step_id': step_id,
            'status': 'executing'
        })
        
    except Exception as e:
        logger.error(f"Error adding wizard step: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
