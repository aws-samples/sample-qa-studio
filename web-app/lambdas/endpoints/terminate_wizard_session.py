import json
import os
import boto3
from utils import create_response, get_table_name, get_current_timestamp, require_scopes

dynamodb = boto3.client('dynamodb')
sqs = boto3.client('sqs')
eventbridge = boto3.client('events')

def handler(event, context):
    """
    Terminate a wizard session by updating its status and sending a terminate command.
    
    Path Parameters:
    - sessionId: The wizard session ID to terminate
    - usecaseId: The usecase ID associated with the session
    
    Returns:
    - 200: Session terminated successfully
    - 400: Missing required parameters
    - 403: Insufficient scopes
    - 500: Error terminating session
    """
    # Validate scopes - terminating wizard modifies usecases
    user_identity, error = require_scopes(event, ['api/usecases.write'])
    if error:
        return error
    
    path_params = event.get('pathParameters', {})
    session_id = path_params.get('sessionId')
    usecase_id = path_params.get('usecaseId')
    
    if not session_id or not usecase_id:
        return create_response(400, {'error': 'Missing sessionId or usecaseId'})
    
    table_name = get_table_name()
    
    try:
        # Update execution status to closed
        dynamodb.update_item(
            TableName=table_name,
            Key={
                'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
                'sk': {'S': f'EXECUTION#{session_id}'}
            },
            UpdateExpression='SET wizard_status = :status, completed_at = :completed',
            ExpressionAttributeValues={
                ':status': {'S': 'closed'},
                ':completed': {'S': get_current_timestamp()}
            }
        )
        print(f'Updated execution status to closed for session {session_id}')
        
    except Exception as e:
        print(f'Error updating execution status: {str(e)}')
        # Continue with termination even if update fails
    
    # Send terminate command for graceful shutdown
    command = {
        'action': 'terminate',
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
            print(f'Terminate command sent to Amazon EventBridge for session {session_id}')
        else:
            # Fallback to Amazon SQS (legacy approach)
            queue_url = os.environ['WIZARD_QUEUE_URL']
            sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(command)
            )
            print(f'Terminate command sent to SQS for session {session_id}')
        
        return create_response(200, {'status': 'terminated'})
        
    except Exception as e:
        print(f'Error sending terminate command: {str(e)}')
        return create_response(500, {'error': 'Failed to send terminate command'})
