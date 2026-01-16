import json
import os
import time
import uuid
import boto3
from datetime import datetime, timezone

dynamodb = boto3.client('dynamodb')

def handler(event, context):
    """
    Process wizard commands from EventBridge and store them in DynamoDB.
    Commands are auto-deleted after 1 hour using TTL.
    
    EventBridge Event Detail:
    - action: Command action (restart, terminate, add_step, etc.)
    - sessionId: Wizard session ID
    - stepId: Optional step ID
    
    Returns:
    - None (EventBridge handler)
    """
    print(f"Received EventBridge event: {event.get('detail-type')}")
    
    # Parse command from event detail
    detail = event.get('detail', {})
    action = detail.get('action')
    session_id = detail.get('sessionId')
    step_id = detail.get('stepId')
    
    if not action or not session_id:
        print(f'Invalid command: missing action or sessionId')
        return
    
    print(f'Processing command: {action} for session: {session_id}')
    
    table_name = os.environ['TABLE_NAME']
    
    # Generate command ID and timestamp
    command_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    timestamp = now.strftime('%Y%m%d%H%M%S.%f')
    
    # Create command record
    item = {
        'pk': {'S': f'WIZARD_COMMAND#{session_id}'},
        'sk': {'S': f'COMMAND#{timestamp}#{command_id}'},
        'command_id': {'S': command_id},
        'action': {'S': action},
        'session_id': {'S': session_id},
        'created_at': {'S': now.strftime('%Y-%m-%dT%H:%M:%SZ')},
        'ttl': {'N': str(int((now.timestamp() + 3600)))}  # Auto-delete after 1 hour
    }
    
    # Add optional step_id
    if step_id:
        item['step_id'] = {'S': step_id}
    
    try:
        # Write to DynamoDB
        dynamodb.put_item(
            TableName=table_name,
            Item=item
        )
        print(f'Command {command_id} written to DynamoDB for session {session_id}')
        
    except Exception as e:
        print(f'Error writing command to DynamoDB: {str(e)}')
        raise
