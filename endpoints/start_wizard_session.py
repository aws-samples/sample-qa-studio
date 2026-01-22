import json
import os
import uuid
import boto3
from utils import create_response, get_table_name, get_current_timestamp, generate_uuid7

dynamodb = boto3.client('dynamodb')
ecs = boto3.client('ecs')

def handler(event, context):
    """
    Start a wizard session by creating a usecase, execution, and ECS task.
    
    Request Body:
    - name: Name of the wizard session (required)
    - starting_url: Starting URL for the wizard (required)
    - description: Optional description
    - region: AWS region for execution
    - model_id: Model ID (defaults to nova-act-v1.0)
    - tags: Optional list of tags
    
    Returns:
    - 201: Wizard session created successfully
    - 400: Missing required fields
    - 500: Error creating session
    """
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})
    
    name = body.get('name', '').strip()
    starting_url = body.get('starting_url', '').strip()
    description = body.get('description', '')
    executing_region = body.get('executing_region', '').strip()
    # Use default region if empty
    if not executing_region:
        executing_region = os.environ.get('DEFAULT_REGION', 'us-east-1')
    model_id = body.get('model_id', 'nova-act-v1.0')
    tags = body.get('tags', [])
    
    # Validate required fields
    if not name or not starting_url:
        return create_response(400, {'error': 'name and starting_url are required'})
    
    print(f'Starting wizard session: name={name}, starting_url={starting_url}, executing_region={executing_region}')
    
    table_name = get_table_name()
    
    # Generate IDs (UUIDv7 for time-ordered sorting)
    usecase_id = generate_uuid7()
    session_id = generate_uuid7()
    created_at = get_current_timestamp()
    
    try:
        # Create usecase record
        dynamodb.put_item(
            TableName=table_name,
            Item={
                'pk': {'S': 'USECASES'},
                'sk': {'S': f'USECASE#{usecase_id}'},
                'id': {'S': usecase_id},
                'name': {'S': name},
                'description': {'S': description},
                'starting_url': {'S': starting_url},
                'active': {'BOOL': True},
                'tags': {'L': [{'S': tag} for tag in tags]},
                'created_at': {'S': created_at},
                'executing_region': {'S': executing_region},
                'model_id': {'S': model_id}
            }
        )
        print(f'Created usecase {usecase_id}')
        
        # Create wizard execution record
        dynamodb.put_item(
            TableName=table_name,
            Item={
                'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
                'sk': {'S': f'EXECUTION#{session_id}'},
                'starting_url': {'S': starting_url},
                'status': {'S': 'pending'},
                'created_at': {'S': created_at},
                'trigger_type': {'S': 'Wizard'},
                'executing_region': {'S': executing_region},
                'model_id': {'S': model_id},
                'mode': {'S': 'wizard'},
                'wizard_status': {'S': 'active'},
                'last_activity': {'S': created_at}
            }
        )
        print(f'Created execution {session_id} for usecase {usecase_id}')
        
        # Start ECS task in wizard mode
        ecs.run_task(
            cluster=os.environ['ECS_CLUSTER'],
            taskDefinition=os.environ['ECS_TASK_DEFINITION'],
            launchType='FARGATE',
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': [os.environ['SUBNET_ID']],
                    'securityGroups': [os.environ['SECURITY_GROUP_ID']],
                    'assignPublicIp': 'ENABLED'
                }
            },
            overrides={
                'containerOverrides': [{
                    'name': 'container',
                    'environment': [
                        {'name': 'WORKER_MODE', 'value': 'wizard'},
                        {'name': 'SESSION_ID', 'value': session_id},
                        {'name': 'USECASE_ID', 'value': usecase_id},
                        {'name': 'WIZARD_QUEUE_URL', 'value': os.environ['WIZARD_QUEUE_URL']},
                        {'name': 'DYNAMODB_TABLE_NAME', 'value': table_name},
                        {'name': 'S3_BUCKET', 'value': os.environ['S3_BUCKET']},
                        {'name': 'BEDROCK_EXECUTION_ROLE', 'value': os.environ['BEDROCK_EXECUTION_ROLE']},
                        {'name': 'NOVA_ACT_API_KEY_NAME', 'value': os.environ['NOVA_ACT_API_KEY_NAME']}
                    ]
                }]
            }
        )
        print(f'Started ECS task for wizard session {session_id}')
        
        return create_response(201, {
            'sessionId': session_id,
            'usecaseId': usecase_id,
            'status': 'initializing'
        })
        
    except Exception as e:
        print(f'Error starting wizard session: {str(e)}')
        return create_response(500, {'error': 'Failed to start wizard session'})
