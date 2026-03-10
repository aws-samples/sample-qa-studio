import json
import os
import boto3
from utils import create_response, require_scopes

sqs = boto3.client('sqs')
eventbridge = boto3.client('events')

def handler(event, context):
    """
    Restart a wizard session by sending a restart command.
    Supports both Amazon EventBridge (new) and Amazon SQS (legacy) approaches.
    
    Path Parameters:
    - sessionId: The wizard session ID to restart
    
    Returns:
    - 200: Restart command sent successfully
    - 400: Missing sessionId
    - 403: Insufficient scopes
    - 500: Error sending command
    """
    # Validate scopes - restarting wizard modifies usecases
    user_identity, error = require_scopes(event, ['api/usecases.write'])
    if error:
        return error
    
    session_id = event.get('pathParameters', {}).get('sessionId')
    
    if not session_id:
        return create_response(400, {'error': 'Missing sessionId'})
    
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
