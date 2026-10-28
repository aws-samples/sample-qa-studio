import lambda_init  # noqa: F401 — must be first import (adds dependencies/ to sys.path)

import json
import os
import boto3
from pydantic import ValidationError
from recording_models import WizardSessionRequest
from resource_auth import require_resource_access, wizard_session_from_path
from utils import create_response, validate_path_id

sqs = boto3.client('sqs')
eventbridge = boto3.client('events')

@require_resource_access('edit', wizard_session_from_path, scopes=['api/usecases.write'])
def handler(event, context):
    """
    Restart a wizard session by sending a restart command.
    Supports both Amazon EventBridge (new) and Amazon SQS (legacy) approaches.
    
    Path Parameters:
    - sessionId: The wizard session ID to restart

    Request Body (WizardSessionRequest):
    - usecaseId: The use case the session belongs to (required)
    
    Returns:
    - 200: Restart command sent successfully
    - 400: Missing sessionId or usecaseId
    - 403: Insufficient scopes or no edit access to the use case
    - 404: Session not found under the use case
    - 500: Error sending command
    """
    session_id, error = validate_path_id(event.get('pathParameters', {}).get('sessionId'), 'session ID')
    if error:
        return error
    try:
        WizardSessionRequest(**json.loads(event.get('body') or '{}'))
    except (TypeError, ValueError, ValidationError):
        return create_response(400, {'error': 'usecaseId is required'})
    
    # Prepare restart command
    command = {
        'action': 'restart',
        'sessionId': session_id
    }
    
    event_bus_name = os.environ.get('WIZARD_EVENT_BUS_NAME')
    
    try:
        if event_bus_name:
            # Send to Amazon EventBridge (new approach)
            eventbridge.put_events(
                Entries=[{
                    'Source': 'wizard.commands',
                    'DetailType': 'WizardCommand',
                    'Detail': json.dumps(command),
                    'EventBusName': event_bus_name
                }]
            )
            print(f'Restart command sent to Amazon EventBridge for session {session_id}')
        else:
            # Fallback to Amazon SQS (legacy approach)
            queue_url = os.environ['WIZARD_QUEUE_URL']
            sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(command)
            )
            print(f'Restart command sent to SQS for session {session_id}')
        
        return create_response(200, {'status': 'restarting'})
        
    except Exception as e:
        print(f'Error sending restart command: {str(e)}')
        return create_response(500, {'error': 'Failed to send restart command'})
