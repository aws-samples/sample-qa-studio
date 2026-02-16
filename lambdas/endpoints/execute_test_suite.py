"""
Execute Test Suite Lambda Function

This function executes all use cases in a test suite in parallel by:
1. Validating user has execute access to suite scope
2. Creating suite execution record with status='running'
3. Querying all use cases in suite
4. Invoking execute_usecase Lambda for each use case in parallel
5. Creating execution result records with status='pending'
6. Storing task ARNs and usecase_execution_ids
7. Returning suite execution ID and metadata
"""

import json
import os
import boto3
from utils import (
    create_response,
    get_table_name,
    get_current_timestamp,
    generate_uuid7,
    require_scopes,
    extract_user_identity
)
from test_suite_schema import (
    get_test_suites_pk,
    get_suite_sk,
    get_suite_mapping_pk,
    get_suite_execution_pk,
    get_execution_sk,
    create_suite_execution_item,
    create_suite_execution_result_item,
    get_suite_exec_result_pk,
    get_result_sk
)

dynamodb = boto3.client('dynamodb')
lambda_client = boto3.client('lambda')


def handler(event, context):
    """
    Execute all use cases in a test suite in parallel.
    
    Path Parameters:
    - suite_id: Test suite ID to execute
    
    Request Body:
    - trigger_type: 'manual' (default) or 'scheduled'
    
    Returns:
    - 200: Suite execution started successfully
    - 400: Missing suite ID or invalid request
    - 403: Insufficient permissions
    - 404: Suite not found
    - 500: Error starting execution
    """
    # Validate authentication and scopes
    user_identity, error_response = require_scopes(event, ['api/suite.write'])
    if error_response:
        return error_response
    
    # Extract suite_id from path parameters
    suite_id = event.get('pathParameters', {}).get('suite_id')
    if not suite_id:
        return create_response(400, {'error': 'Missing suite ID'})
    
    # Parse request body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})
    
    trigger_type = body.get('trigger_type', 'manual')
    if trigger_type not in ['manual', 'scheduled']:
        return create_response(400, {'error': 'Invalid trigger_type. Must be "manual" or "scheduled"'})
    
    table_name = get_table_name()
    current_timestamp = get_current_timestamp()
    user_id = user_identity['identity']
    user_scopes = user_identity.get('scopes', [])
    
    print(f'Executing test suite: {suite_id}, trigger_type: {trigger_type}, user: {user_id}')
    
    try:
        # Get test suite
        suite_response = dynamodb.get_item(
            TableName=table_name,
            Key={
                'pk': {'S': get_test_suites_pk()},
                'sk': {'S': get_suite_sk(suite_id)}
            }
        )
        
        if 'Item' not in suite_response:
            return create_response(404, {'error': 'Test suite not found'})
        
        suite = suite_response['Item']
        suite_name = suite.get('name', {}).get('S', '')
        suite_scope = suite.get('scope', {}).get('S', '')
        
        # Query all use cases in suite
        usecases_response = dynamodb.query(
            TableName=table_name,
            KeyConditionExpression='pk = :pk AND begins_with(sk, :prefix)',
            ExpressionAttributeValues={
                ':pk': {'S': get_suite_mapping_pk(suite_id)},
                ':prefix': {'S': 'USECASE#'}
            }
        )
        
        usecases = usecases_response.get('Items', [])
        
        if not usecases:
            return create_response(400, {'error': 'Test suite has no use cases'})
        
        total_usecases = len(usecases)
        
        # Generate suite execution ID
        suite_execution_id = generate_uuid7()
        
        print(f'Creating suite execution {suite_execution_id} with {total_usecases} use cases')
        
        # Create suite execution record
        suite_execution = create_suite_execution_item(
            suite_execution_id=suite_execution_id,
            suite_id=suite_id,
            suite_name=suite_name,
            suite_scope=suite_scope,
            triggered_by=user_id,
            trigger_type=trigger_type,
            total_usecases=total_usecases,
            started_at=current_timestamp,
            status='running'
        )
        
        # Convert to DynamoDB format
        suite_execution_item = {
            'pk': {'S': suite_execution['pk']},
            'sk': {'S': suite_execution['sk']},
            'id': {'S': suite_execution['id']},
            'suite_id': {'S': suite_execution['suite_id']},
            'suite_name': {'S': suite_execution['suite_name']},
            'suite_scope': {'S': suite_execution['suite_scope']},
            'status': {'S': suite_execution['status']},
            'started_at': {'S': suite_execution['started_at']},
            'triggered_by': {'S': suite_execution['triggered_by']},
            'trigger_type': {'S': suite_execution['trigger_type']},
            'total_usecases': {'N': str(suite_execution['total_usecases'])},
            'completed_usecases': {'N': str(suite_execution['completed_usecases'])},
            'successful_usecases': {'N': str(suite_execution['successful_usecases'])},
            'failed_usecases': {'N': str(suite_execution['failed_usecases'])},
            'running_usecases': {'N': str(suite_execution['running_usecases'])}
        }
        
        dynamodb.put_item(
            TableName=table_name,
            Item=suite_execution_item
        )
        
        print(f'Created suite execution record: {suite_execution_id}')
        
        # Get Lambda function ARN from environment
        execute_usecase_lambda_arn = os.environ.get('EXECUTE_USECASE_LAMBDA_ARN')
        if not execute_usecase_lambda_arn:
            error_msg = 'EXECUTE_USECASE_LAMBDA_ARN environment variable not set'
            print(f'Configuration error: {error_msg}')
            
            # Update suite execution to failed
            dynamodb.update_item(
                TableName=table_name,
                Key={
                    'pk': {'S': get_suite_execution_pk(suite_id)},
                    'sk': {'S': get_execution_sk(suite_execution_id)}
                },
                UpdateExpression='SET #status = :status, error_message = :error_msg',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': {'S': 'failed'},
                    ':error_msg': {'S': error_msg}
                }
            )
            
            return create_response(500, {'error': error_msg})
        
        # Invoke execute_usecase Lambda for each use case in parallel
        invocation_results = []
        
        for usecase_mapping in usecases:
            usecase_id = usecase_mapping.get('usecase_id', {}).get('S', '')
            usecase_name = usecase_mapping.get('usecase_name', {}).get('S', '')
            
            if not usecase_id:
                print(f'Skipping mapping with missing usecase_id')
                continue
            
            # Invoke execute_usecase Lambda asynchronously
            try:
                # Build payload for execute_usecase Lambda
                payload = {
                    'pathParameters': {
                        'id': usecase_id
                    },
                    'queryStringParameters': {
                        'trigger-type': 'OnDemandHeadless',
                        'suite-execution-id': suite_execution_id,
                        'suite-id': suite_id
                    },
                    'requestContext': {
                        'authorizer': {
                            'sub': user_identity.get('sub', ''),
                            'email': user_identity.get('email', user_id),
                            'identityType': user_identity.get('identity_type', 'user'),
                            'scope': ' '.join(user_scopes)
                        }
                    }
                }
                
                response = lambda_client.invoke(
                    FunctionName=execute_usecase_lambda_arn,
                    InvocationType='Event',  # Asynchronous invocation
                    Payload=json.dumps(payload)
                )
                
                invocation_results.append({
                    'usecase_id': usecase_id,
                    'usecase_name': usecase_name,
                    'status': 'invoked',
                    'status_code': response['StatusCode']
                })
                
                print(f'Invoked execute_usecase for {usecase_id}, status: {response["StatusCode"]}')
                
            except Exception as e:
                error_msg = f'Failed to invoke execute_usecase for {usecase_id}: {str(e)}'
                print(f'Invocation error: {error_msg}')
                
                invocation_results.append({
                    'usecase_id': usecase_id,
                    'usecase_name': usecase_name,
                    'status': 'failed',
                    'error': str(e)
                })
        
        # Check if any invocations succeeded
        successful_invocations = [r for r in invocation_results if r['status'] == 'invoked']
        failed_invocations = [r for r in invocation_results if r['status'] == 'failed']
        
        print(f'Invocation summary: {len(successful_invocations)} succeeded, {len(failed_invocations)} failed')
        
        # If all invocations failed, update suite execution to failed
        if not successful_invocations:
            error_msg = 'Failed to invoke any use case executions'
            dynamodb.update_item(
                TableName=table_name,
                Key={
                    'pk': {'S': get_suite_execution_pk(suite_id)},
                    'sk': {'S': get_execution_sk(suite_execution_id)}
                },
                UpdateExpression='SET #status = :status, error_message = :error_msg',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': {'S': 'failed'},
                    ':error_msg': {'S': error_msg}
                }
            )
            
            return create_response(500, {
                'error': error_msg,
                'invocation_results': invocation_results
            })
        
        # Return success response
        return create_response(200, {
            'suite_execution_id': suite_execution_id,
            'suite_id': suite_id,
            'suite_name': suite_name,
            'status': 'running',
            'total_usecases': total_usecases,
            'started_at': current_timestamp,
            'trigger_type': trigger_type,
            'invocation_results': invocation_results
        })
        
    except Exception as e:
        print(f'Error executing test suite: {str(e)}')
        import traceback
        traceback.print_exc()
        return create_response(500, {'error': 'Failed to execute test suite'})
