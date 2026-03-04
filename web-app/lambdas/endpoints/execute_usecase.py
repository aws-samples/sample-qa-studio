import json
import os
import uuid
import boto3
from urllib.parse import quote
from utils import create_response, get_table_name, get_current_timestamp, generate_uuid7, allow_m2m_token

dynamodb = boto3.client('dynamodb')
sqs = boto3.client('sqs')
ecs = boto3.client('ecs')
eventbridge = boto3.client('events')

def generate_cloudwatch_logs_url(region, log_group, stream_prefix, task_id):
    """Generate a deep link to CloudWatch Logs for a specific ECS task."""
    log_stream_name = f"{stream_prefix}/container/{task_id}"
    return (
        f"https://{region}.console.aws.amazon.com/cloudwatch/home?"
        f"region={region}#logsV2:log-groups/log-group/{quote(log_group)}"
        f"/log-events/{quote(log_stream_name)}"
    )

def update_execution_task_info(usecase_id, execution_id, task_arn, task_id, cloudwatch_url):
    """Update the execution record with ECS task metadata."""
    try:
        dynamodb.update_item(
            TableName=get_table_name(),
            Key={
                'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
                'sk': {'S': f'EXECUTION#{execution_id}'}
            },
            UpdateExpression='SET task_arn = :task_arn, task_id = :task_id, cloudwatch_logs_url = :cloudwatch_url',
            ExpressionAttributeValues={
                ':task_arn': {'S': task_arn},
                ':task_id': {'S': task_id},
                ':cloudwatch_url': {'S': cloudwatch_url}
            }
        )
        print(f'Updated execution {execution_id} with task ARN: {task_arn}, task ID: {task_id}')
    except Exception as e:
        print(f'Error updating execution task info: {str(e)}')
        raise

def publish_execution_status_event(usecase_id, execution_id, status):
    """Publish an execution status change event to EventBridge."""
    try:
        event_detail = {
            'usecase_id': usecase_id,
            'execution_id': execution_id,
            'status': status,
            'timestamp': get_current_timestamp()
        }
        
        eventbridge.put_events(
            Entries=[{
                'Source': 'nova-act-qa-studio.execution',
                'DetailType': 'nova-act-qa-studio.execution.status.changed',
                'Detail': json.dumps(event_detail),
                'EventBusName': 'default'
            }]
        )
        print(f'Published execution status event: {usecase_id}/{execution_id} -> {status}')
    except Exception as e:
        print(f'Error publishing event to EventBridge: {str(e)}')
        # Don't fail the execution if event publishing fails

def update_execution_status_with_error(usecase_id, execution_id, status, error_msg):
    """Update execution status and log error details."""
    try:
        dynamodb.update_item(
            TableName=get_table_name(),
            Key={
                'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
                'sk': {'S': f'EXECUTION#{execution_id}'}
            },
            UpdateExpression='SET #status = :status, completed_at = :completed_at, error_message = :error_msg',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': {'S': status},
                ':completed_at': {'S': get_current_timestamp()},
                ':error_msg': {'S': error_msg}
            }
        )
        print(f'Updated execution {execution_id} status to {status} with error: {error_msg}')
        publish_execution_status_event(usecase_id, execution_id, status)
    except Exception as e:
        print(f'Error updating execution status: {str(e)}')


def handler(event, context):
    """
    Execute a usecase by creating an execution record and starting an ECS task.
    Supports OnDemand (queue), Scheduled, OnDemandHeadless (direct ECS), and ci_runner trigger types.
    Accessible by both user tokens and M2M tokens.
    
    Path Parameters:
    - id: Usecase ID to execute
    
    Query Parameters:
    - trigger-type: OnDemand (default), Scheduled, OnDemandHeadless, or ci_runner
    
    Trigger Types:
    - OnDemand: Queues execution to SQS for worker processing
    - Scheduled: Directly spawns ECS task (used by EventBridge Scheduler)
    - OnDemandHeadless: Directly spawns ECS task (used by UI for immediate execution)
    - ci_runner: Creates execution record only, no ECS task (used by CI/CD runner)
    
    Returns:
    - 200: Execution started successfully
    - 400: Missing usecase ID or invalid trigger type
    - 401: Unauthorized
    - 500: Error starting execution
    """
    # Validate authentication (allow both user and M2M tokens)
    user_identity, error_response = allow_m2m_token(event)
    if error_response:
        return error_response
    
    print(f"Execution requested by: {user_identity['identity']} (type: {user_identity['identity_type']})")
    
    usecase_id = event.get('pathParameters', {}).get('id')
    if not usecase_id:
        return create_response(400, {'error': 'Missing usecase ID'})
    
    query_params = event.get('queryStringParameters') or {}
    trigger_type = query_params.get('trigger-type', 'OnDemand')
    suite_execution_id = query_params.get('suite-execution-id')  # Optional: for suite executions
    suite_id = query_params.get('suite-id')  # Optional: for suite executions
    
    # Validate trigger type
    valid_trigger_types = ['OnDemand', 'Scheduled', 'OnDemandHeadless', 'ci_runner']
    if trigger_type not in valid_trigger_types:
        return create_response(400, {
            'error': f'Invalid trigger type: {trigger_type}. Valid values: {", ".join(valid_trigger_types)}'
        })
    
    print(f'usecaseID: {usecase_id}, triggertype: {trigger_type}, suite_execution_id: {suite_execution_id}, suite_id: {suite_id}')
    
    table_name = get_table_name()
    created_at = get_current_timestamp()
    
    try:
        # Load usecase
        usecase_result = dynamodb.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': 'USECASES'},
                'sk': {'S': f'USECASE#{usecase_id}'}
            }
        )
        
        if 'Item' not in usecase_result:
            return create_response(404, {'error': 'Usecase not found'})
        
        usecase = usecase_result['Item']
        print(usecase)
        starting_url = usecase.get('starting_url', {}).get('S', '')
        # Get executing_region from usecase, use default if empty or missing
        region = usecase.get('executing_region', {}).get('S', '').strip()
        if not region:
            region = os.environ.get('DEFAULT_REGION', 'us-east-1')
        model_id = usecase.get('model_id', {}).get('S', '')
        
        # Generate execution ID (UUIDv7 for time-ordered sorting)
        execution_id = generate_uuid7()
        
        # Create execution record
        execution_item = {
            'pk': {'S': f'USECASE_EXECUTION#{usecase_id}'},
            'sk': {'S': f'EXECUTION#{execution_id}'},
            'starting_url': {'S': starting_url},
            'status': {'S': 'pending'},
            'created_at': {'S': created_at},
            'trigger_type': {'S': trigger_type},
            'executing_region': {'S': region},
            'model_id': {'S': model_id}
        }
        
        # Add suite_execution_id and suite_id if this is part of a suite execution
        if suite_execution_id:
            execution_item['suite_execution_id'] = {'S': suite_execution_id}
            print(f'Execution is part of suite execution: {suite_execution_id}')
        
        if suite_id:
            execution_item['suite_id'] = {'S': suite_id}
            print(f'Execution is part of suite: {suite_id}')
        
        dynamodb.put_item(
            TableName=table_name,
            Item=execution_item
        )
        print(f'Created execution {execution_id}')
        
        # Publish pending status event
        publish_execution_status_event(usecase_id, execution_id, 'pending')
        
        # Load and copy steps
        steps_result = dynamodb.query(
            TableName=table_name,
            KeyConditionExpression='pk = :pk AND begins_with(sk, :prefix)',
            ExpressionAttributeValues={
                ':pk': {'S': f'USECASE#{usecase_id}'},
                ':prefix': {'S': 'STEP#'}
            }
        )
        
        steps = steps_result.get('Items', [])
        # Sort by sort field
        steps.sort(key=lambda x: int(x.get('sort', {}).get('N', '0')))
        
        # Create execution step records
        for step in steps:
            step_execution_id = generate_uuid7()
            
            execution_step = {
                'pk': {'S': f'EXECUTION#{execution_id}'},
                'sk': {'S': f'EXECUTION_STEP#{step_execution_id}'},
                'created_at': {'S': created_at}
            }
            
            # Copy required fields
            if 'id' in step:
                execution_step['step_id'] = step['id']
            if 'sort' in step:
                execution_step['sort'] = step['sort']
            if 'instruction' in step:
                execution_step['instruction'] = step['instruction']
            if 'step_type' in step:
                execution_step['step_type'] = step['step_type']
            
            # Copy optional fields if present
            for field in ['secret_key', 'validation_type', 'validation_operator', 
                         'validation_value', 'capture_variable', 'assertion_variable', 'value_type', 'enable_advanced_click_types',
                         'cached_steps', 'cache_last_updated']:
                if field in step:
                    execution_step[field] = step[field]
            
            # Propagate enable_cache from usecase to each execution step
            enable_cache = usecase.get('enable_cache', {})
            if enable_cache:
                execution_step['enable_cache'] = enable_cache
            
            dynamodb.put_item(TableName=table_name, Item=execution_step)
        
        print(f'Created {len(steps)} execution steps')

        
        # Load and copy hooks
        try:
            hooks_result = dynamodb.get_item(
                TableName=table_name,
                Key={
                    'pk': {'S': f'USECASE#{usecase_id}'},
                    'sk': {'S': 'HOOKS'}
                }
            )
            
            if 'Item' in hooks_result:
                hooks = hooks_result['Item']
                execution_hooks = {
                    'pk': {'S': f'EXECUTION#{execution_id}'},
                    'sk': {'S': 'HOOKS'},
                    'created_at': {'S': created_at}
                }
                
                if 'before_script' in hooks:
                    execution_hooks['before_script'] = hooks['before_script']
                if 'after_script' in hooks:
                    execution_hooks['after_script'] = hooks['after_script']
                
                dynamodb.put_item(TableName=table_name, Item=execution_hooks)
                print('Copied hooks to execution')
        except Exception as e:
            print(f'Error copying hooks: {str(e)}')
        
        # Load and copy variables
        try:
            variables_result = dynamodb.get_item(
                TableName=table_name,
                Key={
                    'pk': {'S': f'USECASE#{usecase_id}'},
                    'sk': {'S': 'USECASE_VARIABLES'}
                }
            )
            
            if 'Item' in variables_result:
                variables = variables_result['Item']
                execution_variables = {
                    'pk': {'S': f'EXECUTION#{execution_id}'},
                    'sk': {'S': 'EXECUTION_VARIABLES'},
                    'created_at': {'S': created_at}
                }
                
                if 'variables' in variables:
                    execution_variables['variables'] = variables['variables']
                
                dynamodb.put_item(TableName=table_name, Item=execution_variables)
                print('Copied variables to execution')
        except Exception as e:
            print(f'Error copying variables: {str(e)}')
        
        # Load and copy headers
        try:
            headers_result = dynamodb.get_item(
                TableName=table_name,
                Key={
                    'pk': {'S': f'USECASE#{usecase_id}'},
                    'sk': {'S': 'HEADERS'}
                }
            )
            
            if 'Item' in headers_result:
                headers = headers_result['Item']
                execution_headers = {
                    'pk': {'S': f'EXECUTION#{execution_id}'},
                    'sk': {'S': 'HEADERS'},
                    'created_at': {'S': created_at}
                }
                
                if 'headers' in headers:
                    execution_headers['headers'] = headers['headers']
                
                dynamodb.put_item(TableName=table_name, Item=execution_headers)
                print('Copied headers to execution')
        except Exception as e:
            print(f'Error copying headers: {str(e)}')
        
        # Handle different trigger types
        if trigger_type == 'OnDemand':
            # Send message to SQS queue
            queue_message = {
                'execution_id': execution_id,
                'usecase_id': usecase_id
            }
            
            sqs.send_message(
                QueueUrl=os.environ['QUEUE_URL'],
                MessageBody=json.dumps(queue_message)
            )
            
            return create_response(200, {
                'status': 'usecase queued',
                'usecaseId': usecase_id
            })
        
        elif trigger_type in ['Scheduled', 'OnDemandHeadless']:
            # Start ECS task directly
            print(f'Trigger ECS: {usecase_id}, {execution_id}')
            
            # Determine the correct S3 bucket based on execution region
            s3_bucket_prefix = os.environ['S3_BUCKET_PREFIX']
            execution_region = region if region else os.environ['DEFAULT_REGION']
            s3_bucket = f'{s3_bucket_prefix}-{execution_region}'
            
            print(f'Using S3 bucket for region {execution_region}: {s3_bucket}')

            
            # Create ECS task
            try:
                task_result = ecs.run_task(
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
                                {'name': 'AWS_REGION', 'value': os.environ['AWS_REGION']},
                                {'name': 'EXECUTION_ID', 'value': execution_id},
                                {'name': 'USECASE_ID', 'value': usecase_id},
                                {'name': 'DYNAMODB_TABLE_NAME', 'value': table_name},
                                {'name': 'S3_BUCKET', 'value': s3_bucket},
                                {'name': 'S3_BUCKET_PREFIX', 'value': s3_bucket_prefix},
                                {'name': 'USER_AGENT', 'value': os.environ.get('USER_AGENT', '')},
                                {'name': 'BEDROCK_EXECUTION_ROLE', 'value': os.environ['BEDROCK_EXECUTION_ROLE']},
                                {'name': 'NOVA_ACT_API_KEY_NAME', 'value': os.environ['NOVA_ACT_API_KEY_NAME']},
                                {'name': 'SECRETS_PREFIX', 'value': os.environ['SECRETS_PREFIX']}
                            ]
                        }]
                    }
                )
                
                # Check for task failures
                if task_result.get('failures'):
                    failure = task_result['failures'][0]
                    error_msg = f"Task failed to start - Reason: {failure.get('reason', 'Unknown')}, Detail: {failure.get('detail', 'No details')}"
                    print(f'ECS task failure: {error_msg}')
                    update_execution_status_with_error(usecase_id, execution_id, 'failed', error_msg)
                    return create_response(500, {'error': error_msg})
                
                # Verify at least one task was created
                if not task_result.get('tasks'):
                    error_msg = 'No tasks were created by ECS RunTask'
                    print(f'ECS error: {error_msg}')
                    update_execution_status_with_error(usecase_id, execution_id, 'failed', error_msg)
                    return create_response(500, {'error': error_msg})
                
                # Extract task ARN and ID
                task = task_result['tasks'][0]
                task_arn = task['taskArn']
                
                # Extract task ID from ARN (format: arn:aws:ecs:region:account:task/cluster-name/task-id)
                task_id = task_arn.split('/')[-1]
                
                print(f'ECS task started - ARN: {task_arn}, ID: {task_id}')
                
                # Generate CloudWatch Logs URL
                aws_region = os.environ['AWS_REGION']
                log_group = os.environ.get('LOG_GROUP_NAME', '/ecs/nova-act-worker')
                stream_prefix = os.environ.get('LOG_STREAM_PREFIX', 'ecs')
                
                cloudwatch_url = generate_cloudwatch_logs_url(aws_region, log_group, stream_prefix, task_id)
                print(f'CloudWatch Logs URL: {cloudwatch_url}')
                
                # Update execution with task metadata
                update_execution_task_info(usecase_id, execution_id, task_arn, task_id, cloudwatch_url)
                
                return create_response(200, {
                    'status': 'task started',
                    'usecaseId': usecase_id,
                    'executionId': execution_id,
                    'taskArn': task_arn,
                    'taskId': task_id,
                    'cloudWatchLogsUrl': cloudwatch_url
                })
                
            except Exception as e:
                error_msg = f'Failed to start ECS task: {str(e)}'
                print(f'Error starting ECS task: {error_msg}')
                update_execution_status_with_error(usecase_id, execution_id, 'failed', error_msg)
                return create_response(500, {'error': error_msg})
        
        elif trigger_type == 'ci_runner':
            # CI/CD runner execution: create execution record only, no ECS task
            print(f'CI/CD runner execution created: {execution_id}')
            return create_response(200, {
                'status': 'execution created',
                'usecaseId': usecase_id,
                'executionId': execution_id
            })
        
        else:
            # Should never reach here due to validation above, but keep for safety
            return create_response(400, {'error': f'Invalid trigger type: {trigger_type}'})
    
    except Exception as e:
        print(f'Error executing usecase: {str(e)}')
        return create_response(500, {'error': 'Failed to execute usecase'})
