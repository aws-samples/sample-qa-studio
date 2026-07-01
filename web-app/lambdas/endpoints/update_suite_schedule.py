import logging
import json
import os
import boto3
import re
from typing import Any, Dict
from botocore.exceptions import ClientError
from utils import (
    create_response,
    get_table_name,
    get_current_timestamp,
    require_scopes,
    validate_path_id)
from test_suite_schema import (
    get_test_suites_pk,
    get_suite_sk,
    get_suite_update_expression
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def validate_cron_expression(expression: str) -> bool:
    """
    Validate cron expression format (basic validation).
    
    Supports standard cron format: minute hour day month day-of-week
    Example: "0 2 * * *" (runs at 2 AM daily)
    
    Args:
        expression: Cron expression string
        
    Returns:
        True if valid, False otherwise
    """
    if not expression or not isinstance(expression, str):
        return False
    
    parts = expression.strip().split()
    
    # Cron expression should have 5 parts
    if len(parts) != 5:
        return False
    
    # Basic pattern validation for each part
    # Allows: numbers, *, -, /, and ,
    cron_pattern = r'^[\d\*\-\/,]+$'
    
    for part in parts:
        if not re.match(cron_pattern, part):
            return False
    
    return True


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to update test suite schedule configuration.
    
    Validates user has write access to suite scope, updates schedule fields
    on suite entity, and manages EventBridge rule (create/update/disable).
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with updated test suite
    """
    try:
        # Extract suite_id from path parameters
        path_params = event.get('pathParameters', {})
        suite_id, error = validate_path_id(event.get('pathParameters', {}).get('suite_id'), 'suite ID')
        if error:
            return error
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid JSON in request body'})
        
        # Validate scope access (requires api/suite.write or admin)
        user_identity, error_response = require_scopes(event, ['api/suite.write'])
        if error_response:
            return error_response
        
        logger.info(f"Updating schedule for test suite {suite_id} for user: {user_identity.get('identity')}")
        
        # Extract schedule fields from body
        schedule_enabled = body.get('schedule_enabled')
        schedule_expression = body.get('schedule_expression')
        schedule_timezone = body.get('schedule_timezone')
        
        # Validate at least one field is provided
        if schedule_enabled is None and schedule_expression is None and schedule_timezone is None:
            return create_response(400, {
                'error': 'At least one schedule field (schedule_enabled, schedule_expression, schedule_timezone) must be provided'
            })
        
        # Validate schedule_enabled type
        if schedule_enabled is not None and not isinstance(schedule_enabled, bool):
            return create_response(400, {'error': 'schedule_enabled must be a boolean'})
        
        # Validate cron expression if provided
        if schedule_expression is not None:
            schedule_expression = schedule_expression.strip()
            if not schedule_expression:
                return create_response(400, {'error': 'schedule_expression cannot be empty'})
            if not validate_cron_expression(schedule_expression):
                return create_response(400, {
                    'error': 'Invalid cron expression format. Expected format: "minute hour day month day-of-week" (e.g., "0 2 * * *")'
                })
        
        # Validate timezone if provided
        if schedule_timezone is not None:
            schedule_timezone = schedule_timezone.strip()
            if not schedule_timezone:
                return create_response(400, {'error': 'schedule_timezone cannot be empty'})
        
        # Initialize Amazon DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Get existing suite to validate it exists
        response = table.get_item(
            Key={
                'pk': get_test_suites_pk(),
                'sk': get_suite_sk(suite_id)
            }
        )
        
        # Check if suite exists
        if 'Item' not in response:
            logger.warning(f"Test suite {suite_id} not found")
            return create_response(404, {'error': 'Test suite not found'})
        
        suite = response['Item']
        
        # Update timestamp
        now = get_current_timestamp()
        
        # Build update expression for DynamoDB
        update_expression, expression_values, expression_names = get_suite_update_expression(
            schedule_enabled=schedule_enabled,
            schedule_expression=schedule_expression,
            schedule_timezone=schedule_timezone,
            updated_at=now
        )
        
        # Update the suite in DynamoDB
        update_kwargs = {
            'Key': {
                'pk': get_test_suites_pk(),
                'sk': get_suite_sk(suite_id)
            },
            'UpdateExpression': update_expression,
            'ExpressionAttributeValues': expression_values,
            'ReturnValues': 'ALL_NEW'
        }
        if expression_names:
            update_kwargs['ExpressionAttributeNames'] = expression_names
        
        update_response = table.update_item(**update_kwargs)
        
        updated_suite = update_response['Attributes']
        
        # Manage Amazon EventBridge rule
        try:
            manage_eventbridge_rule(
                suite_id=suite_id,
                schedule_enabled=updated_suite.get('schedule_enabled', False),
                schedule_expression=updated_suite.get('schedule_expression'),
                schedule_timezone=updated_suite.get('schedule_timezone')
            )
        except Exception as e:
            logger.error(f"Error managing EventBridge rule: {str(e)}", exc_info=True)
            return create_response(500, {
                'error': 'Failed to update Amazon EventBridge rule',
                'message': str(e)
            })
        
        logger.info(f"Successfully updated schedule for test suite {suite_id}")
        
        # Return the updated suite (remove pk/sk from response)
        response_suite = {k: v for k, v in updated_suite.items() if k not in ['pk', 'sk']}
        
        return create_response(200, response_suite)
        
    except Exception as e:
        logger.error(f"Error updating suite schedule: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})


def manage_eventbridge_rule(
    suite_id: str,
    schedule_enabled: bool,
    schedule_expression: str = None,
    schedule_timezone: str = None
) -> None:
    """
    Manage Amazon EventBridge rule for suite scheduling.
    
    Creates/updates rule if schedule_enabled=True, disables if False.
    
    Args:
        suite_id: Test suite ID
        schedule_enabled: Whether scheduling is enabled
        schedule_expression: Cron expression
        schedule_timezone: Timezone for schedule
        
    Raises:
        Exception: If EventBridge operations fail
    """
    # Get environment variables
    base_name = os.environ.get('BASE_NAME', 'accept-ai')
    execute_suite_lambda_arn = os.environ.get('EXECUTE_SUITE_LAMBDA_ARN')
    
    if not execute_suite_lambda_arn:
        raise ValueError('EXECUTE_SUITE_LAMBDA_ARN environment variable not set')
    
    # Initialize Amazon EventBridge client
    events_client = boto3.client('events')
    
    # Rule naming convention
    rule_name = f'{base_name}-suite-{suite_id}'
    
    if schedule_enabled:
        # Create or update EventBridge rule
        if not schedule_expression:
            raise ValueError('schedule_expression is required when schedule_enabled is True')
        
        # Convert 5-field unix cron to 6-field EventBridge format.
        # EventBridge requires exactly one of day-of-month or day-of-week to be '?'.
        parts = schedule_expression.split()
        if len(parts) == 5:
            day_of_month, day_of_week = parts[2], parts[4]
            if day_of_month == '*' and day_of_week == '*':
                parts[4] = '?'
            elif day_of_week == '*':
                parts[4] = '?'
            elif day_of_month == '*':
                parts[2] = '?'
            parts.append('*')
        eventbridge_expression = f'cron({" ".join(parts)})'
        
        logger.info(f"Creating/updating EventBridge rule: {rule_name} with expression: {eventbridge_expression}")
        
        # Create or update the rule
        events_client.put_rule(
            Name=rule_name,
            ScheduleExpression=eventbridge_expression,
            State='ENABLED',
            Description=f'Schedule for test suite {suite_id}'
        )
        
        # Add Lambda target to the rule
        target_input = {
            'pathParameters': {'suite_id': suite_id},
            'body': json.dumps({'trigger_type': 'scheduled'})
        }
        
        events_client.put_targets(
            Rule=rule_name,
            Targets=[
                {
                    'Id': '1',
                    'Arn': execute_suite_lambda_arn,
                    'Input': json.dumps(target_input)
                }
            ]
        )
        
        logger.info(f"EventBridge rule {rule_name} enabled successfully")
        
    else:
        # Disable the EventBridge rule (don't delete it)
        try:
            logger.info(f"Disabling EventBridge rule: {rule_name}")
            events_client.disable_rule(Name=rule_name)
            logger.info(f"EventBridge rule {rule_name} disabled successfully")
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logger.info(f"EventBridge rule {rule_name} does not exist, nothing to disable")
            else:
                raise
